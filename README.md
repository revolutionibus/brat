# A try to add bangla rendering at Terminal (BRAT)

Terminal Neovim puts every grapheme cluster in one cell and never shapes it, so
Bangla conjuncts break, ি lands after its consonant and vowel signs collide.

**BanglaCells** works around that without touching your text:

1. `tools/build_font.py` shapes thousands of Bangla clusters (ক্ষ, কি, স্ত্রী, র্কা …)
   with HarfBuzz, so the GSUB conjuncts, vowel reordering and GPOS mark positions
   are all applied, and flattens each result into **one glyph sized to one terminal cell**.
   The glyphs live in Supplementary Private Use Area-B (U+100000+), away from Nerd Font icons.
2. The Neovim plugin (`lua/bangla_cells`) conceals each cluster on screen with
   its private-use character. The buffer, search, yank and saved file stay normal Unicode.

## Requirements

- Neovim 0.10+ (grapheme-cluster cells), HarfBuzz (`brew install harfbuzz`), Python 3 with `fonttools`
- A Bangla source font. Default: `~/Library/Fonts/NotoSansBengali-VariableFont.ttf`
  (its `wdth=62.5` condensed instance fits a monospace cell almost exactly)

## Build

```sh
python3 tools/build_font.py                 # build/BanglaCells.ttf + lua/bangla_cells/map.lua
python3 tools/build_font.py --install       # ...and copy the font to ~/Library/Fonts
```

Useful options:

| Option | Effect |
|---|---|
| `--mono PATH [--mono-index N]` | size glyphs to your terminal font's cell (`.ttc` needs an index) |
| `--mono PATH --merge` | write `build/<font>-Bangla.ttf`, a copy of your terminal font with the Bangla glyphs added (family `"<Family> Bangla"`); use this if your terminal does not fall back to BanglaCells |
| `--corpus FILES/DIRS` | also pre-render every cluster found in your own text |
| `--extra FILE` | add clusters listed one per line (defaults to the plugin's missing log) |
| `--wdth`, `--wght` | instance of a variable source font |

Rebuilding keeps the existing codepoints, so an old font and a new map never
disagree about clusters both contain. Restart the terminal after installing a new font.

## Neovim setup

```lua
vim.opt.rtp:append("/Users/mdatiqurrahman/python_codes/brat")
require("bangla_cells").setup()   -- auto-enables in buffers containing Bangla
```

Options for `setup()`: `auto` (true), `concealcursor` ("nvic"), `log_missing` (true),
`missing_file` (`stdpath("state")/bangla_cells_missing.txt`), `keymap` ("probhat"),
`insert_maps` ({}).

### Typing Bangla

`insert_maps` adds Normal-mode keys that enter Insert mode with the Bangla keymap
on. `Esc` switches back to English, so plain `i`/`a`/`o` keep typing English:

```lua
require("bangla_cells").setup({
  insert_maps = {
    ["<leader>ni"] = "i", ["<leader>na"] = "a", ["<leader>no"] = "o",
    ["<leader>nI"] = "I", ["<leader>nA"] = "A", ["<leader>nO"] = "O",
  },
})
```

Commands:

- `:BanglaCells [on|off|toggle]`: switch the rendering for the current buffer
- `:BanglaInsert [i|a|o|I|A|O]`: enter Insert mode typing Bangla
- `:BanglaCellsMissing`: open the log of clusters the font does not have yet; rebuild to add them

## Limits

- One cell per cluster: wide conjuncts are drawn condensed.
- The headline (মাত্রা) has small gaps between cells.
- The terminal must find the font: either through system fallback (standalone font)
  or by using the `--merge` font as the terminal's main font.
