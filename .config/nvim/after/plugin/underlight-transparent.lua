local transparent_groups = {
  "Normal",
  "NormalNC",
  "NormalFloat",
  "FloatBorder",
  "SignColumn",
  "FoldColumn",
  "EndOfBuffer",
  "LineNr",
  "NeoTreeNormal",
  "NeoTreeNormalNC",
  "NvimTreeNormal",
  "NvimTreeNormalNC",
  "TelescopeNormal",
  "TelescopeBorder",
}

local function clear_backgrounds()
  for _, name in ipairs(transparent_groups) do
    local ok, highlight = pcall(vim.api.nvim_get_hl, 0, {
      name = name,
      link = false,
    })
    if ok then
      highlight.bg = nil
      highlight.ctermbg = nil
      vim.api.nvim_set_hl(0, name, highlight)
    end
  end
end

local group = vim.api.nvim_create_augroup("UnderlightTransparency", { clear = true })
vim.api.nvim_create_autocmd("ColorScheme", {
  group = group,
  callback = function() vim.schedule(clear_backgrounds) end,
})
vim.schedule(clear_backgrounds)
