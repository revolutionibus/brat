-- Show Bangla with pre-shaped glyphs from the BanglaCells font.
--
-- The buffer text is never changed. Each grapheme cluster Neovim draws in one
-- cell (ক্ষ, কি, স্ত্রী, ...) is concealed with a private-use codepoint whose glyph,
-- built by tools/build_font.py, is that cluster already shaped by HarfBuzz.
local M = {}

local api = vim.api
local bit = require("bit")

local ns = api.nvim_create_namespace("bangla_cells")
local MAYBE_BANGLA = "\224[\165-\167]"   -- UTF-8 lead bytes for U+0940–U+09FF
local BENGALI = "\224[\166\167]"         -- U+0980–U+09FF only

local config = {
  auto = true,              -- enable automatically in buffers that contain Bangla
  concealcursor = "nvic",   -- keep glyphs on the cursor line in every mode
  log_missing = true,       -- record clusters the font lacks, for the next rebuild
  missing_file = vim.fn.stdpath("state") .. "/bangla_cells_missing.txt",
  keymap = "probhat",       -- input keymap used by M.insert()
  insert_maps = {},         -- normal-mode lhs -> insert command, e.g. { ["<leader>ni"] = "i" }
}

local map                 -- cluster -> codepoint, loaded on first use
local chars = {}          -- codepoint -> UTF-8 string
local segments, nsegments = {}, 0   -- line text -> { {col, end_col, char}, ... }
local enabled = {}        -- bufnr -> true
local saved = {}          -- winid -> { conceallevel, concealcursor }
local missing_seen, missing_queue = nil, {}

local function load_map()
  if map == nil then
    local ok, m = pcall(require, "bangla_cells.map")
    if not ok then
      vim.notify("bangla_cells: no glyph map; run tools/build_font.py first", vim.log.levels.ERROR)
      m = false
    end
    map = m
  end
  return map
end

local function utf8_char(cp)
  local c = chars[cp]
  if not c then
    c = string.char(0xF0 + bit.rshift(cp, 18), 0x80 + bit.band(bit.rshift(cp, 12), 0x3F),
                    0x80 + bit.band(bit.rshift(cp, 6), 0x3F), 0x80 + bit.band(cp, 0x3F))
    chars[cp] = c
  end
  return c
end

local function flush_missing()
  local f = io.open(config.missing_file, "a")
  if f then
    f:write(table.concat(missing_queue, "\n"), "\n")
    f:close()
  end
  missing_queue = {}
end

local function log_missing(cluster)
  if not missing_seen then
    missing_seen = {}
    local f = io.open(config.missing_file, "r")
    if f then
      for l in f:lines() do missing_seen[l] = true end
      f:close()
    end
  end
  if missing_seen[cluster] then return end
  missing_seen[cluster] = true
  missing_queue[#missing_queue + 1] = cluster
  if #missing_queue == 1 then vim.schedule(flush_missing) end
end

local function segment(line)
  local segs = segments[line]
  if segs then return segs end
  segs = {}
  local col = 0
  for _, c in ipairs(vim.fn.split(line, [[\zs]])) do
    local cp = map[c]
    if cp then
      segs[#segs + 1] = { col, col + #c, utf8_char(cp) }
    elseif config.log_missing and c:find(BENGALI) then
      log_missing(c)
    end
    col = col + #c
  end
  if nsegments >= 20000 then segments, nsegments = {}, 0 end
  segments[line], nsegments = segs, nsegments + 1
  return segs
end

api.nvim_set_decoration_provider(ns, {
  on_win = function(_, _, buf)
    return enabled[buf] == true
  end,
  on_line = function(_, _, buf, row)
    local line = api.nvim_buf_get_lines(buf, row, row + 1, false)[1]
    if not line or not line:find(MAYBE_BANGLA) then return end
    for _, s in ipairs(segment(line)) do
      api.nvim_buf_set_extmark(buf, ns, row, s[1],
        { end_col = s[2], conceal = s[3], ephemeral = true })
    end
  end,
})

local function apply_win(win)
  if saved[win] then return end
  saved[win] = { vim.wo[win].conceallevel, vim.wo[win].concealcursor }
  vim.wo[win].conceallevel = 2
  vim.wo[win].concealcursor = config.concealcursor
end

local function restore_win(win)
  local s = saved[win]
  if not s then return end
  saved[win] = nil
  if api.nvim_win_is_valid(win) then
    vim.wo[win].conceallevel, vim.wo[win].concealcursor = s[1], s[2]
  end
end

function M.enable(buf)
  buf = (buf == nil or buf == 0) and api.nvim_get_current_buf() or buf
  if not load_map() then return end
  enabled[buf] = true
  for _, win in ipairs(vim.fn.win_findbuf(buf)) do apply_win(win) end
  vim.cmd.redraw({ bang = true })
end

function M.disable(buf)
  buf = (buf == nil or buf == 0) and api.nvim_get_current_buf() or buf
  enabled[buf] = nil
  for _, win in ipairs(vim.fn.win_findbuf(buf)) do restore_win(win) end
  vim.cmd.redraw({ bang = true })
end

function M.toggle(buf)
  buf = (buf == nil or buf == 0) and api.nvim_get_current_buf() or buf
  if enabled[buf] then M.disable(buf) else M.enable(buf) end
end

function M.is_enabled(buf)
  return enabled[(buf == nil or buf == 0) and api.nvim_get_current_buf() or buf] == true
end

-- Enter Insert mode with {cmd} (i, a, o, I, A, O, ...) and the Bangla keymap
-- on. Leaving Insert mode switches back to English, so a plain `i` stays English.
function M.insert(cmd)
  if vim.bo.keymap == "" then vim.bo.keymap = config.keymap end
  vim.bo.iminsert = 1
  local buf = api.nvim_get_current_buf()
  api.nvim_create_autocmd("InsertLeave", {
    buffer = buf,
    once = true,
    callback = function() vim.bo[buf].iminsert = 0 end,
  })
  api.nvim_feedkeys(cmd or "i", "in", false)   -- ahead of pending keys
end

function M.open_missing()
  vim.cmd.edit(vim.fn.fnameescape(config.missing_file))
end

local function has_bangla(buf, first, last)
  for _, l in ipairs(api.nvim_buf_get_lines(buf, first, last, false)) do
    if l:find(BENGALI) then return true end
  end
  return false
end

function M.setup(opts)
  config = vim.tbl_extend("force", config, opts or {})
  local group = api.nvim_create_augroup("bangla_cells", { clear = true })

  for lhs, cmd in pairs(config.insert_maps) do
    vim.keymap.set("n", lhs, function() M.insert(cmd) end,
      { desc = "Insert Bangla (" .. cmd .. ")" })
  end

  -- A window that starts showing an enabled buffer gets the conceal options;
  -- one that switches to another buffer gets its own options back.
  api.nvim_create_autocmd("BufWinEnter", {
    group = group,
    callback = function(ev)
      local win = api.nvim_get_current_win()
      if enabled[ev.buf] then
        apply_win(win)
      elseif config.auto and has_bangla(ev.buf, 0, 500) then
        M.enable(ev.buf)
      else
        restore_win(win)
      end
    end,
  })
  if config.auto then
    api.nvim_create_autocmd({ "TextChanged", "TextChangedI" }, {
      group = group,
      callback = function(ev)
        if enabled[ev.buf] then return end
        local row = api.nvim_win_get_cursor(0)[1]
        if has_bangla(ev.buf, row - 1, row) then M.enable(ev.buf) end
      end,
    })
  end
  api.nvim_create_autocmd("BufWipeout", {
    group = group,
    callback = function(ev) enabled[ev.buf] = nil end,
  })
  api.nvim_create_autocmd("WinClosed", {
    group = group,
    callback = function(ev) saved[tonumber(ev.match)] = nil end,
  })
end

return M
