local launcher = vim.fn.expand("~/.local/bin/underlight-rag")

if vim.fn.executable(launcher) ~= 1 then
  return
end

local function terminal(args)
  vim.cmd("botright 15new")
  vim.fn.termopen(vim.list_extend({ launcher }, args))
  vim.cmd("startinsert")
end

vim.api.nvim_create_user_command("RagAsk", function(options)
  local function run(question)
    if question and question ~= "" then
      terminal({ "ask", question })
    end
  end
  if options.args ~= "" then
    run(options.args)
  else
    vim.ui.input({ prompt = "RAG question: " }, run)
  end
end, { nargs = "*", desc = "Ask Underlight RAG with local context" })

vim.api.nvim_create_user_command("RagIndex", function(options)
  local source = options.args ~= "" and options.args or "projects"
  local args = { "index", "--table", source }
  if options.bang then
    table.insert(args, "--rebuild")
  end
  terminal(args)
end, {
  nargs = "?",
  bang = true,
  complete = function()
    return { "projects", "downloads", "home", "all" }
  end,
  desc = "Index an Underlight RAG source; use ! to rebuild",
})

vim.api.nvim_create_user_command("RagStatus", function()
  terminal({ "status" })
end, { desc = "Show Underlight RAG status" })

if vim.fn.maparg("<leader>ar", "n") == "" then
  vim.keymap.set("n", "<leader>ar", "<cmd>RagAsk<cr>", {
    desc = "Ask local RAG",
    silent = true,
  })
end
