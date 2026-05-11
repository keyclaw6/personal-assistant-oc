import { defineSetupPluginEntry } from "openclaw/plugin-sdk/channel-core";
import { messengerPlugin } from "./src/channel.js";
export default defineSetupPluginEntry(messengerPlugin);
