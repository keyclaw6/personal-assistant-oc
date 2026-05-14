import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { registerComposioLimitedTools } from "./src/composio-tools.js";

export default definePluginEntry({
  id: "composio-limited",
  name: "Composio Limited",
  description: "Restricted Composio tools for Gmail, Calendar, Google Tasks, and LinkedIn.",
  register(api) {
    registerComposioLimitedTools(api);
  },
});
