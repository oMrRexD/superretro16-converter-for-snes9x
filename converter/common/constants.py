"""Cross-module constants for the converter package.

Module-local constants that are only used within one module stay there:
- ``_GAUSS_TABLE`` -> ``audio_brr``
- ``MARKER_KEYS`` / ``MARKER_LEN`` / ``SR16_MAGIC`` -> ``sr16_codec``
- ``SNES9X_HEADER`` / ``SNES9X_VERSION`` -> ``snes9x_io``
- ``CHIP_CHUNK_NAMES`` -> ``pipeline``

This file is the single source of truth for SNES hardware register addresses,
chunk sizes, internal chunk-byte offsets, and a few small magic numbers that
appear in more than one module. Grouping them here keeps the actual extractor
code readable and prevents the same constant from drifting between callers.
"""
from __future__ import annotations

# ============================================================================
# SR16 chunk sizes used by the converter
# ============================================================================
SR16_C01_SIZE = 161        # CPU regs + timings
SR16_P01_SIZE = 2645       # PPU state (different field order than snes9x)
SR16_D01_SIZE = 152        # DMA state (8 channels x 19B)
SR16_VR1_SIZE = 0x10000    # 64KB VRAM
SR16_RM1_SIZE = 0x20000    # 128KB WRAM
SR16_F01_SIZE = 0x8000     # 32KB FillRAM (hardware register mirror)
SR16_A01_SIZE = 248        # APU/SPC700 registers
SR16_AR1_SIZE = 0x10000    # 64KB APU/SPC RAM
SR16_SPC_SIZE = 68608      # Old combined Blargg APU snapshot
SR16_SSZ_SIZE = 1281       # Old Snes9x SoundData / DSP voice pipeline state
SR16_SAX_SIZE = 71         # Old SuperFX state
SR16_SA1_SIZE = 83         # Old SA-1 register/state payload
SR16_PSD_SIZE = 1450       # DSP-1/2/4 state (single shared header)
SR16_4XC_SIZE = 8192       # Cx4 RAM
SR16_SRAM_SIZE = 0x20000   # 128KB SRAM section stored by SR16

# ============================================================================
# snes9x v12 chunk sizes (from snapshot.cpp FreezeData[])
# ============================================================================
SNES_CPU_SIZE = 48         # SCPUState (12 fields x 4B BE)
SNES_REG_SIZE = 16         # PB DB P A D S X Y PC
SNES_TIM_SIZE = 70         # STimings (mixed widths)
SNES_PPU_SIZE = 2652       # SPPU (snes9x SnapPPU layout)
SNES_DMA_SIZE = 152        # SDMA[8]
SNES_DMA_CHANNELS = 8
SNES_DMA_CHANNEL_SIZE = 19
SNES_SND_SIZE = 66560      # APU snapshot (RAM+SMP+DSP+sched+CPU ports+pad)
SNES_DP4_SIZE = 1297       # DSP-4 (SDSP4)
SNES_SFX_SIZE = 996        # SuperFX
SNES_SA1_SIZE = 60         # SA-1 main state (without registers)
SNES_SAR_SIZE = 16         # SA-1 registers (same shape as REG)
SNES_BSX_SIZE = 147        # BS-X
SNES_SRT_SIZE = 8          # S-RTC
SNES_CLK_SIZE = 20         # RTC
SNES_OBC_SIZE = 6          # OBC1
SNES_OBM_SIZE = 8192       # OBC1 memory
SNES_ST0_SIZE = 35         # ST010

# snes9x stores SRAM padded to 512KB regardless of cart size
SRAM_TARGET_SIZE = 0x80000

# ============================================================================
# SR16 framebuffer + snes9x SHO screenshot dimensions
# ============================================================================
SR16_SCREEN_WIDTH = 256
SR16_SCREEN_HEIGHT = 224
SR16_SCREEN_BYTES = SR16_SCREEN_WIDTH * SR16_SCREEN_HEIGHT * 2
SHO_MAX_WIDTH = 512
SHO_MAX_HEIGHT = 478
SHO_DATA_BYTES = SHO_MAX_WIDTH * SHO_MAX_HEIGHT * 3

# ============================================================================
# SNES hardware register addresses (FillRAM mirror offsets in F01)
# ============================================================================
NMITIMEN     = 0x4200      # IRQ enable + auto-joypad (bit4=H IRQ, bit5=V IRQ)
HTIMEL       = 0x4207      # H-IRQ position low 8b
HTIMEH       = 0x4208      # H-IRQ position high bit
VTIMEL       = 0x4209      # V-IRQ position low 8b
VTIMEH       = 0x420A      # V-IRQ position high bit
MDMAEN       = 0x420B      # General DMA enable bitmask (1B)
HDMAEN       = 0x420C      # HDMA enable bitmask (1B)

# DMA channel registers ($43x0..$43x7, 8 channels)
DMA_REGS_BASE   = 0x4300
DMA_CH_STRIDE   = 0x10
DMA_REGS_END    = 0x4380   # = DMA_REGS_BASE + 8 * DMA_CH_STRIDE

# Per-channel offsets within DMA_REGS_BASE + ch*DMA_CH_STRIDE
DMA_OFF_DMAP    = 0x00     # control
DMA_OFF_BBAD    = 0x01     # B-bus dest (low byte of $21xx)
DMA_OFF_A1TL    = 0x02     # A-bus addr low
DMA_OFF_A1TH    = 0x03     # A-bus addr mid
DMA_OFF_A1B     = 0x04     # A-bus bank
DMA_OFF_DASL    = 0x05     # DMA count / HDMA indirect addr low
DMA_OFF_DASH    = 0x06     # DMA count / HDMA indirect addr high
DMA_OFF_DASB    = 0x07     # HDMA indirect bank

# B-bus ports the converter pre-executes
BBUS_CGDATA = 0x22         # writes to $2122
BBUS_OAMDATA = 0x04        # writes to $2104

# PPU registers (used as F01 offsets via FillRAM mirror)
W12SEL    = 0x2123         # Window 1/2 enable for BG1/BG2
W34SEL    = 0x2124         # Window 1/2 enable for BG3/BG4
WOBJSEL   = 0x2125         # Window 1/2 enable for OBJ/Color
WH0       = 0x2126         # Window 1 Left
WH1       = 0x2127         # Window 1 Right
WH2       = 0x2128         # Window 2 Left
WH3       = 0x2129         # Window 2 Right
WBGLOG    = 0x212A         # Window mask logic for BG
WOBJLOG   = 0x212B         # Window mask logic for OBJ/Color
COLDATA   = 0x2132         # Fixed color data + select bits
PPU_WIN_RANGE_START = W12SEL    # range start, inclusive
PPU_WIN_RANGE_END   = COLDATA   # range end, exclusive

# DSP registers (offsets within DSP regs[128] = A01[$38..$B8])
DSP_REG_MVOL_L = 0x0C      # master volume left
DSP_REG_EFB    = 0x0D      # echo feedback
DSP_REG_MVOL_R = 0x1C      # master volume right
DSP_REG_PMON = 0x2D        # pitch modulation enable bitmask
DSP_REG_EVOL_L = 0x2C      # echo volume left
DSP_REG_EVOL_R = 0x3C      # echo volume right
DSP_REG_NON  = 0x3D        # noise enable bitmask
DSP_REG_EON  = 0x4D        # echo enable bitmask
DSP_REG_DIR  = 0x5D        # sample directory base (high byte)
DSP_REG_FLG  = 0x6C        # bit5 = echo write disable
DSP_REG_ESA  = 0x6D        # echo start address (high byte)
DSP_REG_ENDX = 0x7C        # voice end-of-sample (sticky)
DSP_REG_EDL  = 0x7D        # echo delay length (low 4 bits = pages)

# ============================================================================
# snes9x SnapPPU layout offsets
# (from converter/sr16_to_snes9x/state/ppu_remap.py SNES9X_LAYOUT)
# ============================================================================
PPU_OFF_CGADD          = 62
PPU_OFF_CG_SAVED_BYTE  = 63
PPU_OFF_CGDATA         = 64        # 256 entries x 2B BE = 512B
PPU_OFF_OAMADDR        = 1992      # word index, 2B BE
PPU_OFF_OAMDATA        = 2003      # 544B
PPU_OFF_HTIMER_ENABLED = 2549
PPU_OFF_VTIMER_ENABLED = 2550
PPU_OFF_HTIMER_POS     = 2551      # i16 BE
PPU_OFF_VTIMER_POS     = 2553      # i16 BE
PPU_OFF_IRQ_H_BEAM     = 2555      # u16 BE
PPU_OFF_IRQ_V_BEAM     = 2557      # u16 BE
PPU_OFF_HBEAM_LATCH    = 2561      # u16 BE
PPU_OFF_GUN_V_LATCH    = 2567      # u16 BE
PPU_OFF_WIN1_LEFT      = 2595
PPU_OFF_WIN1_RIGHT     = 2596
PPU_OFF_WIN2_LEFT      = 2597
PPU_OFF_WIN2_RIGHT     = 2598
PPU_OFF_RECOMPUTE_CLIP = 2599
PPU_OFF_CLIP_BLOCK     = 2600      # 6 slots x 6B (BG1..4 + OBJ + Color)
PPU_CLIP_SLOT_STRIDE   = 6
PPU_OFF_FIXED_COLOR_R  = 2637
PPU_OFF_FIXED_COLOR_G  = 2638
PPU_OFF_FIXED_COLOR_B  = 2639
PPU_OFF_HDMA_BYTE      = 2646
PPU_OFF_HDMA_ENDED     = 2647

# Per-clip-slot byte offsets (within a 6-byte slot at PPU_OFF_CLIP_BLOCK + n*6)
CLIP_OFF_WIN1_ENABLE  = 2
CLIP_OFF_WIN2_ENABLE  = 3
CLIP_OFF_WIN1_INSIDE  = 4
CLIP_OFF_WIN2_INSIDE  = 5

# CGRAM
CGRAM_BYTES   = 512
CGRAM_ENTRIES = 256

# OAM
OAM_BYTES = 544

# ============================================================================
# snes9x SCPUState (CPU chunk) offsets — only the fields we touch
# ============================================================================
CPU_OFF_CYCLES         = 0
CPU_OFF_PREV_CYCLES    = 4
CPU_OFF_V_COUNTER      = 8
CPU_OFF_FLAGS          = 12
CPU_OFF_FAST_ROM_SPEED = 28
CPU_OFF_WHICH_EVENT    = 37
CPU_OFF_NEXT_EVENT     = 38
CPU_OFF_WAITING_FOR_INTERRUPT = 42
CPU_OFF_NMI_PENDING    = 43

# snes9x event constants (CPU.WhichEvent)
HC_HDMA_INIT_EVENT = 4
HC_RENDER_EVENT    = 5

# snes9x STimings (TIM chunk) offsets
TIM_OFF_H_MAX_MASTER = 0
TIM_OFF_H_MAX        = 4
TIM_OFF_V_MAX        = 12
TIM_OFF_HDMA_INIT    = 20
TIM_OFF_WRAM_REFRESH = 36
TIM_OFF_INTERLACE    = 44
TIM_OFF_IRQ_TRIGGER  = 61
TIM_OFF_NEXT_IRQ     = 66

# Default IRQ scheduler "no IRQ pending" sentinel (snes9x convention)
NO_IRQ_PENDING       = 0x0FFFFFFF
NO_IRQ_PENDING_INIT  = 0x000FFFFF   # initial TIM.NextIRQTimer

# ============================================================================
# snes9x SND chunk internal layout
# ============================================================================
SND_OFF_SPC_RAM = 0
SND_OFF_SMP     = 65536
SND_SMP_FIELDS  = 41                       # all LE int32
SND_SMP_BYTES   = SND_SMP_FIELDS * 4       # 164
SND_OFF_DSP     = SND_OFF_SMP + SND_SMP_BYTES   # 65700
SND_DSP_BYTES   = 642
SND_OFF_TAIL    = SND_OFF_DSP + SND_DSP_BYTES   # 66342
SND_TAIL_BYTES  = 16
SND_TAIL_CPU_PORTS_REL = 12                # CPU/APU ports inside tail

# SMP field indices within the snes9x SND block (all LE int32)
SMP_FIELD_PC = 3
SMP_FIELD_SP = 4
SMP_FIELD_A = 5
SMP_FIELD_X = 6
SMP_FIELD_Y = 7
SMP_FIELD_PSW_BASE = 8
SMP_FIELD_IPL_ROM = 16
SMP_FIELD_TIMER_BASE = 20
SMP_TIMER_STRIDE_FIELDS = 5
SMP_TIMER_FIELD_ENABLE = 0
SMP_TIMER_FIELD_TARGET = 1
SMP_TIMER_FIELD_STAGE3 = 3

# DSP::save_state internal layout (SPC_DSP::copy_state)
DSP_OFF_REGS          = 0           # 128B
DSP_OFF_VOICES        = 128         # 8 voices x 38B = 304B
DSP_VOICE_STRIDE      = 38
DSP_REG_VOICE_STRIDE  = 0x10        # visible DSP voice register stride
DSP_VREG_VOL_L        = 0
DSP_VREG_VOL_R        = 1
DSP_VREG_PITCH_L      = 2
DSP_VREG_PITCH_H      = 3
DSP_VREG_ADSR1        = 5
DSP_VREG_ADSR2        = 6
DSP_OFF_ECHO_HIST     = 432         # 8 stereo pairs x 4B = 32B
DSP_OFF_MISC          = 464         # 49B misc fields
DSP_OFF_EXTERNAL_REGS = 513         # mirror of regs at save time

# Per-voice offsets within voice block (38B)
VOICE_OFF_BUF12        = 0          # int16[12] = 24B
VOICE_OFF_INTERP_POS   = 24         # u16
VOICE_OFF_BRR_ADDR     = 26         # u16
VOICE_OFF_ENV          = 28         # u16
VOICE_OFF_HIDDEN_ENV   = 30         # i16
VOICE_OFF_BUF_POS      = 32         # u8
VOICE_OFF_BRR_OFFSET   = 33         # u8
VOICE_OFF_KON_DELAY    = 34         # u8
VOICE_OFF_ENV_MODE     = 35         # u8
VOICE_OFF_T_ENVX_OUT   = 36         # u8

# DSP misc field offsets (named ABSOLUTE within DSP block, not relative)
DSP_MISC_KON           = DSP_OFF_MISC + 1    # 465
DSP_MISC_ECHO_OFFSET   = DSP_OFF_MISC + 6    # 470 (u16)
DSP_MISC_ECHO_LENGTH   = DSP_OFF_MISC + 8    # 472 (u16)
DSP_MISC_NEW_KON       = DSP_OFF_MISC + 11   # 475
DSP_MISC_ENDX_BUF      = DSP_OFF_MISC + 12   # 476
DSP_MISC_ENVX_BUF      = DSP_OFF_MISC + 13   # 477
DSP_MISC_OUTX_BUF      = DSP_OFF_MISC + 14   # 478
DSP_MISC_T_PMON        = DSP_OFF_MISC + 15   # 479
DSP_MISC_T_NON         = DSP_OFF_MISC + 16   # 480
DSP_MISC_T_EON         = DSP_OFF_MISC + 17   # 481
DSP_MISC_T_DIR         = DSP_OFF_MISC + 18   # 482
DSP_MISC_T_KOFF        = DSP_OFF_MISC + 19   # 483
DSP_MISC_T_ESA         = DSP_OFF_MISC + 26   # 490
DSP_MISC_T_ECHO_EN     = DSP_OFF_MISC + 27   # 491

# A01 (SR16 APU snapshot) offsets
A01_OFF_WAIT_COUNTER   = 0x00     # 4B BE
A01_OFF_Y              = 0x04
A01_OFF_A              = 0x05
A01_OFF_X              = 0x06
A01_OFF_SP             = 0x07
A01_OFF_PSW            = 0x08
A01_OFF_CYCLES         = 0x09     # 4B BE
A01_OFF_PC             = 0x0D     # 2B BE
A01_OFF_IPL_ROM        = 0x1F
A01_OFF_KEYED          = 0x24
A01_OFF_OUT_PORTS      = 0x25     # 4B (SMP -> CPU mailbox)
A01_OFF_TIMER          = 0x29     # 3 x 2B BE
A01_OFF_TIMER_TARGET   = 0x2F     # 3 x 2B BE
A01_OFF_TIMER_ENABLED  = 0x35     # 3B
A01_OFF_DSP_REGS       = 0x38     # 128B
A01_OFF_EXTRA_RAM      = 0xB8     # 64B
A01_TIMER_COUNT        = 3
A01_EXTRA_RAM_SIZE     = 64

# AR1 (SPC RAM) — CPU -> SMP mailbox lives in SPC's IPL ROM mirror at $F4..$F7
SPC_PORT_F4 = 0xF4
SPC_PORT_COUNT = 4
SPC_DSPADDR = 0xF2
SPC_RAM_F8  = 0xF8
SPC_RAM_F9  = 0xF9

# SSZ (SR16 SoundData) per-voice offsets
SSZ_VOICE_BASE         = 0x30
SSZ_VOICE_STRIDE       = 0x75
SSZ_VOICE_OLD_ENV      = 0x15     # 4B BE (fallback when ext env=0)
SSZ_VOICE_SAMPLE_MODE  = 0x00     # u32 BE
SSZ_VOICE_LOOP_FLAG    = 0x04     # u32 BE
SSZ_VOICE_VOL_L        = 0x08     # i16 BE
SSZ_VOICE_VOL_R        = 0x0A     # i16 BE
SSZ_VOICE_PITCH        = 0x0C     # u32 BE
SSZ_VOICE_ENV          = 0x15     # u32 BE
SSZ_VOICE_LOOP         = 0x27     # u32 BE
SSZ_VOICE_ATTACK_RATE  = 0x2B     # u32 BE
SSZ_VOICE_DECAY_RATE   = 0x2F     # u32 BE
SSZ_VOICE_SUSTAIN_RATE = 0x33     # u32 BE
SSZ_VOICE_GAIN         = 0x3B     # u32 BE
SSZ_VOICE_DECODED      = 0x41     # 16 x 2B BE
SSZ_VOICE_PREV1        = 0x61     # i16 BE (one-back sample)
SSZ_VOICE_PREV2        = 0x63     # i16 BE (two-back sample)
SSZ_VOICE_BLOCK_PTR    = 0x69     # 4B BE (low 16b used)
SSZ_VOICE_SAMPLE_PTR   = 0x6D     # 4B BE
SSZ_EXT_BASE           = 0x3DC
SSZ_EXT_STRIDE         = 0x22
SSZ_EXT_OUT_SAMPLE     = 0x00     # i16 BE
SSZ_EXT_ENV            = 0x02     # 4B BE
SSZ_OFF_ECHO_OFFSET    = 0x10     # u32 BE
SSZ_OFF_ECHO_LENGTH    = 0x14     # u32 BE
SSZ_OFF_NOISE_RATE     = 0x3D8    # u32 BE (old SoundData noise rate)
SSZ_OFF_NOISE_COUNT    = 0x4EC    # u32 BE (old SoundData noise counter)
SSZ_OFF_NO_FILTER      = 0x4F0    # u8
SSZ_OFF_ECHO_VOLUME    = 0x4F1    # 2 x u32 BE
SSZ_OFF_MASTER_VOLUME  = 0x4F9    # 2 x u32 BE

# SR16 register-prefix layout (used by C01 and SA1 prefix)
SR16_REG_OFF_DB        = 0x00
SR16_REG_OFF_P         = 0x01
SR16_REG_OFF_A         = 0x05
SR16_REG_OFF_D         = 0x09
SR16_REG_OFF_S         = 0x0D
SR16_REG_OFF_X         = 0x11
SR16_REG_OFF_Y         = 0x15
SR16_REG_OFF_PC_FULL   = 0x19   # 4B BE: high byte = PB, low 16 = PC

# SR16 C01 extra fields (after the register prefix)
C01_OFF_CYCLES         = 0x21    # 4B BE
C01_OFF_WAITING_FOR_INTERRUPT = 0x34  # 1B
C01_OFF_WHICH_EVENT    = 0x37    # 1B (old snes9x event numbering)
C01_OFF_NEXT_EVENT     = 0x44    # 4B BE
C01_OFF_V_COUNTER      = 0x48    # 4B BE
C01_OFF_FAST_ROM_SPEED = 0x54    # 4B BE
C01_OFF_TIMINGS_H_MAX  = 0x72    # 4B BE
C01_OFF_TIMINGS_V_MAX_M = 0x76   # 4B BE
C01_OFF_TIMINGS_V_MAX   = 0x7A   # 4B BE
C01_OFF_TIMINGS_NMI     = 0x7E   # 4B BE
C01_OFF_TIMINGS_WRAM_REF = 0x82  # 4B BE
C01_OFF_INTERLACE       = 0x86   # 1B

# WRAM bank semantics
WRAM_BANK_LOW       = 0x7E
WRAM_BANK_HIGH      = 0x7F
WRAM_LOW_HALF_BYTES = 0x10000
