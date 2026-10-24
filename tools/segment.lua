-- Split each line of arg[1] into grapheme clusters exactly as Neovim's
-- screen grid does, writing them tab-separated to arg[2].
-- Run with: nvim --clean --headless -l segment.lua IN OUT
local out = assert(io.open(arg[2], "w"))
for line in io.lines(arg[1]) do
  out:write(table.concat(vim.fn.split(line, [[\zs]]), "\t"), "\n")
end
out:close()
