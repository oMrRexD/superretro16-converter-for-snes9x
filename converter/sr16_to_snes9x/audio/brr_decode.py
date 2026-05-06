"""BRR block decoding and SSZ voice-window construction helpers."""
from __future__ import annotations

# Empirical cap on the BRR offset used as a resume position. Resuming at
# offsets 5/7 (i.e. inside the second half of a BRR block) put Blargg's
# next-pair decode at the very tail of the current block and caused loud
# pops in Super Metroid saves where paired instrument voices were already
# mid-phrase. Capping to <= 3 keeps the continuation inside the first half
# of the block; the seeded sample buffer already carries the immediate
# audio history. If a future game exposes a counter-example, raise this
# limit through phase_calibration rather than removing the clamp here.
BRR_RESUME_MAX_OFFSET = 3


def _decode_brr_block(spc_ram: bytes, block_addr: int,
                      prev2: int, prev1: int
                      ) -> tuple[int, list[int], int, int]:
    """Decode one 9-byte BRR block into 16 signed PCM samples.

    `prev2`/`prev1` are the previous two decoded samples used by the BRR
    filters. Returns `(header, samples16, last2, last1)`.
    """
    block_addr &= 0xFFFF
    header = spc_ram[block_addr]
    out: list[int] = []
    p2 = int(prev2)
    p1 = int(prev1)

    for i in range(1, 9):
        byte = spc_ram[(block_addr + i) & 0xFFFF]
        for nibble in (byte >> 4, byte & 0x0F):
            sample = nibble - 16 if nibble & 0x08 else nibble
            shift = header >> 4
            if shift <= 12:
                sample = (sample << shift) >> 1
            else:
                sample &= ~0x7FF

            filt = (header >> 2) & 0x03
            if filt >= 2:
                sample += p1
                sample -= p2 >> 1
                if filt == 2:
                    sample += p2 >> 4
                    sample += (p1 * -3) >> 6
                else:
                    sample += (p1 * -13) >> 7
                    sample += (p2 * 3) >> 4
            elif filt == 1:
                sample += p1 >> 1
                sample += (-p1) >> 5

            sample = max(-32768, min(32767, sample))
            sample = int(sample) * 2
            sample = max(-32768, min(32767, sample))
            out.append(sample)
            p2, p1 = p1, sample

    return header, out, p2, p1

def _next_brr_block_addr(spc_ram: bytes, block_addr: int,
                         loop_addr: int | None) -> int | None:
    """Return the BRR block address that follows `block_addr`."""
    header = spc_ram[block_addr & 0xFFFF]
    if header & 0x01:
        if header & 0x02 and loop_addr is not None:
            return loop_addr & 0xFFFF
        return None
    return (block_addr + 9) & 0xFFFF

def _build_ssz_voice_window(spc_ram: bytes, current_block_addr: int,
                            loop_block_addr: int | None,
                            decoded_block: list[int],
                            prev_last2: tuple[int, int],
                            sample_ptr: int
                            ) -> tuple[list[int], int, int, int]:
    """Translate old SoundData block/sample state to Blargg buffer state.

    Returns `(buf12, interp_pos, next_brr_addr, next_brr_offset)`.

    Phase model:
      Blargg's gaussian reads `in[0..3] = buf[buf_pos+base..buf_pos+base+3]`
      with `base = interp_pos >> 12`. The output sample sits between in[1]
      and in[2] (gauss[255]/gauss[256] are the dominant taps), so the
      "currently-being-emitted" sample lands at `buf[base + 1.5]`. SR16's
      `sample_pointer = K` means decoded[K] is the next sample to emit; the
      previously emitted one was decoded[K-1]. To phase-align, we therefore
      need `buf[base + 1] = decoded[K-1]` and `buf[base + 2] = decoded[K]`.
      That is, the seeded buffer must hold *two samples of history* at
      `buf12[0..1]` followed by current/future samples — not the current
      quartet starting at buf12[0]. Misaligning by 2 samples feeds the
      interpolator samples ~30-60 us in the future, which is the audible
      click on the first frame.
    """
    sample_ptr &= 0x0F
    quartet_index = sample_ptr >> 2
    interp_pos = (sample_ptr & 0x03) * 0x1000

    # `prev_last2` here is `(p2, p1)` in BRR-IIR convention: p2 is two samples
    # back, p1 is one sample back. They are also the last two samples that
    # SR16 emitted before decoded[0] of the current block.
    p2, p1 = prev_last2

    segments: list[tuple[int, int, list[int]]] = []
    next_addr: int | None = current_block_addr & 0xFFFF
    current_decoded = decoded_block[:]
    iir_p2, iir_p1 = p2, p1

    while len(segments) < 4 and next_addr is not None:
        start_quartet = quartet_index if not segments else 0
        for q in range(start_quartet, 4):
            offset = 1 + q * 2
            seg = current_decoded[q * 4:q * 4 + 4]
            if len(seg) == 4:
                segments.append((next_addr, offset, seg))
            if len(segments) >= 4:
                break
        if len(segments) >= 4:
            break

        decoded_last2 = (current_decoded[14], current_decoded[15])
        next_block = _next_brr_block_addr(spc_ram, next_addr, loop_block_addr)
        if next_block is None:
            break
        _header, current_decoded, iir_p2, iir_p1 = _decode_brr_block(
            spc_ram, next_block, decoded_last2[0], decoded_last2[1]
        )
        next_addr = next_block
        quartet_index = 0

    if not segments:
        return [0] * 12, 0, current_block_addr & 0xFFFF, 1

    # Two-sample history that immediately precedes the current quartet.
    # quartet_index here is the original (pre-loop) value of sample_ptr >> 2.
    orig_quartet = (sample_ptr & 0x0F) >> 2
    if orig_quartet == 0:
        history = [int(p2), int(p1)]
    else:
        s0 = decoded_block[orig_quartet * 4 - 2]
        s1 = decoded_block[orig_quartet * 4 - 1]
        history = [int(s0), int(s1)]

    forward: list[int] = []
    for _addr, _off, seg in segments:
        forward.extend(seg)

    # Layout: [hist0, hist1, current_quartet(4), next_quartet(4), pad(2)]
    buf12 = history + forward[:10]
    if len(buf12) < 12:
        buf12.extend([buf12[-1] if buf12 else 0] * (12 - len(buf12)))

    # Pick the next-decode position so that, after Blargg's first
    # decode_brr fires (writing to buf[0..3]) and then advances buf_pos
    # to 4, the chain stays consistent. With buf_pos=0 and the freshly
    # seeded `interp_pos`, the first decode happens after we've already
    # interpolated through buf[0..3] of OUR seed — i.e., the two history
    # samples plus two of the current quartet. We then need brr_addr to
    # provide the next BRR quartet (the 3rd seeded segment) so the
    # waveform continues without re-decoding the current quartet.
    if len(segments) >= 3:
        # Use the 3rd segment as the next-decode source (its 4 samples
        # correspond to forward[8..11], which we did NOT fit into buf12).
        next_brr_addr, next_brr_offset, _seg = segments[2]
    elif len(segments) >= 2:
        next_brr_addr, next_brr_offset, _seg = segments[1]
    else:
        tail_addr, tail_offset, _seg = segments[-1]
        next_brr_addr = tail_addr
        next_brr_offset = tail_offset

    # Blargg reads two BRR data bytes from `brr_addr + brr_offset` when the
    # voice crosses a decode boundary. Resuming with offset 5/7 can put the
    # first post-load decode at the tail of a BRR block, which caused loud pops
    # in Super Metroid saves where paired instrument voices were already mid-
    # phrase. Keep the continuation in the first half of the block; the seeded
    # buffer already carries the immediate audio history.
    if next_brr_offset > BRR_RESUME_MAX_OFFSET:
        next_brr_offset = BRR_RESUME_MAX_OFFSET

    return buf12[:12], interp_pos, next_brr_addr, next_brr_offset
