# Blueprint for Premium Mobile UI/UX & PWA Upgrade
**Target Project:** FebGuy AI (febguyai.vercel.app)
**Author:** Pranav Amble
**Core Directive:** Upgrade the mobile interface to feel premium, minimal, smooth, and simple (matching the UX benchmark of ChatGPT/Gemini). **DO NOT TOUCH, CHANGE, OR DISTURB THE DESKTOP UI/UX BY EVEN 1%.** All desktop workflows, state variables, streaming logic, and desktop CSS layout constraints must remain completely intact.

---

## 1. Project Context & Constraints
* **Main File Layout:** `App.jsx` (~8,000–10,000 lines of code) handles core states, streaming text hooks, and layout rendering.
* **Global Stylesheet:** `style.css` (~7,000+ lines of raw/compiled CSS) containing layout matrices for the desktop workspace.
* **Safety Protocol:** Do NOT request full file refactors. Work exclusively by generating **isolated new sub-components** and appending **scoped mobile-only CSS overrides via media queries**.

---

## 2. Core Execution Strategy
To bypass the risk of breaks in a massive codebase, execute via three distinct separation layers:

```
+--------------------------------------------------------------------------+
|                        FebGuy AI Architecture                            |
+--------------------------------------------------------------------------+
|                                                                          |
|   [ Core React State & API Logic ] ---> Stays Unchanged in App.jsx       |
|                                                                          |
|         /                                      \                         |
|        / (Desktop Viewports)                    \ (Mobile Viewports)     |
|       v                                          v                       |
|   [ Existing Desktop Layout ]               [ Isolated Mobile View ]     |
|   - Multi-pane Grid Layout                  - Fixed bottom input bar     |
|   - Visible sidebars & cards                - Stripped down clutter      |
|   - 100% Intact Legacy CSS                  - Slide-up bottom sheets     |
|                                             - Vaul / Framer Motion       |
|                                             - Media Query overrides      |
+--------------------------------------------------------------------------+
```

### Layer A: CSS Media Query Overrides (The No-JS Safety Layer)
* Append a mobile break rule (`@media screen and (max-width: 767px)`) at the absolute bottom of `style.css`.
* Enforce `display: none !important;` on secondary/tertiary desktop layouts (e.g., permanent sidebar panels, mid-screen workspace limits cards, user layout configurations).
* Force the main chat container elements to structural defaults (`width: 100% !important; margin: 0 !important; padding: 12px !important;`).

### Layer B: Component Isolation for Premium UI Feature Set
* Create standalone functional components inside a separate subdirectory (`src/components/mobile/...`).
* Inject modern animations and mobile-native components into these isolated files so they do not touch main desktop component states.
* **Packages to leverage inside isolated files:**
  * `vaul`: To build hardware-accelerated bottom sheets that slide up elegantly on touch.
  * `framer-motion`: For smooth transition states on message rendering and drawer slide-ins.
  * `lucide-react`: For high-fidelity minimalist mobile icons.

### Layer C: Safe Conditional Injections in App.jsx
* Introduce a clean React viewport listener hook at the root level of `App.jsx` to toggle structural rendering context flags dynamically:
```jsx
const [isMobileViewport, setIsMobileViewport] = useState(false);
useEffect(() => {
  const checkViewport = () => setIsMobileViewport(window.innerWidth < 768);
  checkViewport();
  window.addEventListener('resize', checkViewport);
  return () => window.removeEventListener('resize', checkViewport);
}, []);
```
* Use `isMobileViewport` strictly to conditionally switch layout nodes or show mobile-only components, leaving legacy desktop JSX fully unperturbed.

---

## 3. UI/UX Refinement Benchmarks (Mobile vs. Desktop)

### A. Main Workspace & Layout Clutter
* **Desktop Status:** Looks perfect. Features side-by-side Chat and Code Studio viewports, visible usage metric cards ("Chat messages left", "Code messages left", "File uploads left").
* **Mobile Overhaul:** 
  * Strip out the usage counters, user session labels ("Guest Workspace", "Temporary session"), and workspace cards entirely from the initial viewport layout.
  * Consolidate hidden operational data inside an animated sliding panel or navigation tree hidden behind an overlay.

### B. Chat Prompt Box & Controls
* **Desktop Status:** Integrates an expandable inline search/smart toggle bar flowing inline with the page structure.
* **Mobile Overhaul:**
  * Force the prompt container into a fixed footer: `position: fixed; bottom: 0; left: 0; right: 0; z-index: 999;`.
  * Style it as an isolated capsule layout right above the software keyboard buffer offset.
  * Apply calculated structural offsets to the message container viewport wrapper (`height: calc(100vh - [input-height-offset]); overflow-y: auto; padding-bottom: 24px;`) to ensure message feeds aren't obscured behind the prompt bar.

---

## 4. Progressive Web App (PWA) Integration Specification
To make FebGuy AI discoverable, indexable, and installable as a high-performance native-like app on iOS and Android devices, generate the following standard structures:

### A. Web App Manifest File (`public/manifest.json`)
```json
{
  "short_name": "FebGuyAI",
  "name": "FebGuy AI Private Workspace",
  "icons": [
    {
      "src": "favicon.ico",
      "sizes": "64x64 32x32 24x24 16x16",
      "type": "image/x-icon"
    },
    {
      "src": "logo192.png",
      "type": "image/png",
      "sizes": "192x192",
      "purpose": "any maskable"
    },
    {
      "src": "logo512.png",
      "type": "image/png",
      "sizes": "512x512",
      "purpose": "any maskable"
    }
  ],
  "start_url": ".",
  "display": "standalone",
  "theme_color": "#0b0f19",
  "background_color": "#0b0f19",
  "orientation": "portrait"
}
```

### B. Minimalist Service Worker Setup (`public/sw.js`)
Handles offline fallback wrappers and caches asset bundles without introducing network race conditions into Vercel live deployments.
```javascript
const CACHE_NAME = 'febguyai-cache-v1';
const ASSETS_TO_CACHE = [
  '/',
  '/index.html',
  '/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
});

self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request).then((response) => {
      return response || fetch(event.request);
    })
  );
});
```

---

## 5. Sequential Step-by-Step Prompts for ChatGPT / Codex

When executing this roadmap with an AI assistant, use these exact micro-prompts one by one. **Do not combine them.**

### Step 1: Generating the Mobile Styling Engine Override
> **Prompt to AI:** 
> "I have a live, deployed React application with a 7,000-line global stylesheet `style.css`. The desktop view is absolutely perfect and must not be altered by even 1%. I need to write a clean, isolated `@media screen and (max-width: 767px)` block to append at the absolute bottom of my CSS file. 
> On screens smaller than 768px, I want to hide these clutter elements using `display: none !important`: `.stats-container`, `.messages-left-card`, `.file-uploads-card`, `.guest-workspace-badge`. 
> Also, configure the main layout class `.main-content-wrapper` to be 100% wide with zero margins, and position the prompt bar container class `.input-box-container` to stay fixed at the bottom of the screen (`position: fixed; bottom: 0; width: 100%; z-index: 9999;`). Please write only the media query code block."

### Step 2: Creating the Isolated Slide-Up Mobile Menu Component
> **Prompt to AI:**
> "I want to introduce a premium, smooth mobile menu using the `vaul` package for a slide-up bottom drawer layout. This file must be a brand new, completely separate component called `src/components/mobile/MobileMenu.jsx` so it does not touch my 10,000-line `App.jsx`.
> The component should take `chatMessagesLeft`, `codeMessagesLeft`, and `fileUploadsLeft` as props and render them elegantly inside an unstyled bottom drawer sheet. Provide the component layout code and the simple semantic CSS classes I can use to style it manually."

### Step 3: Injecting the Viewport Listener Safely into App.jsx
> **Prompt to AI:**
> "My main `App.jsx` file contains nearly 10,000 lines of complex React states and streaming API hooks. I cannot paste the entire file here. I want to add a window resize state listener to detect mobile viewports safely. Here is a small 20-line snippet of the top of my main component functions where my states are declared: [Paste small snippet of states here]. 
> Please write the `useState` and `useEffect` window resize hooks, show me exactly where to place them, and explain how to conditionally render the new `<MobileMenu />` component without disturbing any of my existing desktop elements or state management workflows."

---

## 6. Local Quality Control & Risk Management Verification Checklist
1. **Branch Protection:** Run `git checkout -b feature/mobile-premium-upgrade` locally before modifying any codebase assets.
2. **Local Environment Simulation:** Run `npm run dev` and press `F12` to open chrome inspector. Switch device models to iPhone 14 Pro or Pixel 7 Pro to test touch parameters locally.
3. **PWA Diagnostics:** Run a Google Lighthouse Audit locally under the 'Progressive Web App' check categorization to ensure asset manifest mappings resolve properly before staging production builds.
4. **Vercel Safe Staging:** Push changes to a non-main GitHub branch to generate a Vercel **Preview Deployment**. Verify the mobile UI on a real phone using the preview URL before merging to production.
