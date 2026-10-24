if vim.g.loaded_bangla_cells then return end
vim.g.loaded_bangla_cells = 1

vim.api.nvim_create_user_command("BanglaCells", function(opts)
  local bc = require("bangla_cells")
  local action = opts.args ~= "" and opts.args or "toggle"
  if action == "on" then bc.enable() elseif action == "off" then bc.disable() else bc.toggle() end
end, {
  nargs = "?",
  complete = function() return { "on", "off", "toggle" } end,
  desc = "Show Bangla with pre-shaped BanglaCells glyphs",
})

vim.api.nvim_create_user_command("BanglaInsert", function(opts)
  require("bangla_cells").insert(opts.args ~= "" and opts.args or "i")
end, {
  nargs = "?",
  complete = function() return { "i", "a", "o", "I", "A", "O" } end,
  desc = "Enter Insert mode typing Bangla",
})

vim.api.nvim_create_user_command("BanglaCellsMissing", function()
  require("bangla_cells").open_missing()
end, { desc = "Open the log of clusters missing from the BanglaCells font" })
