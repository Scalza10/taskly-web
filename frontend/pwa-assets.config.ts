import { defineConfig, minimal2023Preset } from "@vite-pwa/assets-generator/config";

// npm run icons: makes the PNG icons and favicon in public/ from icon.svg. Run it when the icon changes.
export default defineConfig({ preset: minimal2023Preset, images: ["public/icon.svg"] });
