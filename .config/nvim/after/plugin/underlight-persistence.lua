local workspace = vim.fn.expand("~/.local/bin/ros2-workspace")

if vim.fn.executable(workspace) ~= 1 then
  return
end

vim.api.nvim_create_user_command("UnderlightRos2Workspace", function()
  vim.cmd("botright 15new")
  vim.fn.termopen({ workspace })
  vim.cmd("startinsert")
end, { desc = "Open the persistent Underlight ROS 2 workspace" })

if vim.fn.maparg("<leader>tw", "n") == "" then
  vim.keymap.set("n", "<leader>tw", "<cmd>UnderlightRos2Workspace<cr>", {
    desc = "Persistent ROS2 workspace",
    silent = true,
  })
end
