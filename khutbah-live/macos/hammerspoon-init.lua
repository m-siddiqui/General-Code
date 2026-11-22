-- Optional: use a cheap Bluetooth remote/clicker paired to the Mac Studio as the mimbar button.
-- Install Hammerspoon (free, hammerspoon.org), then paste this into ~/.hammerspoon/init.lua
-- and choose "Reload Config" from the Hammerspoon menu.
--
-- Most clickers send Page Down / Page Up (some send Right / Left arrow instead).
-- Note: while this is loaded, those keys are taken over on the Mac Studio for every app.

local KEY = "PASTE-ACCESS-KEY"
local BASE = "http://127.0.0.1:8080/api/"

local function call(action)
  hs.http.asyncPost(BASE .. action .. "?source=clicker&key=" .. KEY, "", nil, function(status, body)
    hs.alert.show("Khutbah Live: " .. (body or status))
  end)
end

-- Page Down = go live, Page Up = end.  Change the keys to match your clicker.
hs.hotkey.bind({}, "pagedown", function() call("start") end)
hs.hotkey.bind({}, "pageup", function() call("stop") end)
