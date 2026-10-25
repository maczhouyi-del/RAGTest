import {defineConfig} from "vite";

// Keep previous generated assets; cleanup is a separate, explicitly managed action.
export default defineConfig({build: {emptyOutDir: false}});
