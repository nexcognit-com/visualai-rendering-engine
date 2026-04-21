# VisualAI by NexCognit — Master Product Specification

**Document Type:** Master PRD, Architecture, and UI/UX Specification (Cursor-Ready)  
**Project:** VisualAI (AI Marketing Employee SaaS)  
**Author:** Manus AI for Amr Eid, CEO — NexCognit  
**Date:** April 2026  

---

## 1. Executive Summary

The demand for automated, high-quality product marketing content is surging among e-commerce brands and marketing agencies. Traditional product photography and video production are costly ($300–$2,000 per video), time-consuming (3-5 days), and difficult to scale. 

VisualAI is a multi-tenant, credit-based SaaS platform that transforms any product image, URL, or text script into a complete suite of marketing assets in under 60 seconds. It functions as an autonomous "AI Marketing Employee" for e-commerce brands, marketing agencies, and dropshippers.

The core technical strategy is to **fork the open-source MoneyPrinterTurbo (MPT) repository** and modify its source code. We are replacing its generic stock-footage pipeline with a highly specialized, multi-model orchestration layer that dynamically routes requests to the best available APIs for product photography, cinematic B-roll, voice generation, and UGC avatars.

---

## 2. Competitive Landscape

The market for AI product photography and marketing automation is crowded but fragmented. Most tools focus on a single aspect. VisualAI's full-stack approach is a strong differentiator.

### Key Competitors
*   **Creatify:** ($39/mo) Excellent for video ads, but lacks native product photography generation.
*   **Synthesia:** ($29/mo) Great for avatars, but lacks automated product B-roll and photography.
*   **Photoroom:** ($9.99/mo) Dominates static product images but lacks advanced video generation.
*   **Nightjar:** (~$0.10/image) Focuses on visual consistency ("Photography Styles") for static images.
*   **Pictory:** ($19/mo) Good for long-form faceless videos, but lacks UGC avatars and product photography.

**The NexCognit Advantage:** VisualAI is the only platform combining product photography generation (NanoBanana), cinematic B-roll (Veo 3.1), UGC avatars (MuseTalk), and full pipeline automation in a single multi-tenant SaaS. The self-owned rendering engine means zero per-render platform fees — every video rendered is pure margin after API costs.

---

## 3. Core Agent Modes (The 5 Products)

VisualAI exposes five distinct agent modes to the user, all powered by the same underlying rendering engine.

### Mode 1: Product Shoot Generator
*   **Input:** Raw product image (JPEG/PNG/URL).
*   **Output:** 6 professional studio-quality product photographs.
*   **Process:** The Orchestration Layer routes the image to the Image Generation API (e.g., NanoBanana Pro). A 3×2 contact sheet is returned, sliced into 6 individual images via a Python script, and saved to the user's asset library.
*   **Cost:** 5 credits.

### Mode 2: Short Marketing Video Generator
*   **Input:** Product image OR product URL OR custom script.
*   **Output:** 15–60 second vertical video (9:16) for TikTok/Reels.
*   **Process:** The LLM API writes a hook-body-CTA script. The Audio API generates the voiceover. The Video API generates cinematic B-roll. The MPT engine stitches the assets with subtitles and music.
*   **Cost:** 10 credits.

### Mode 3: Long-Form Product Marketing Video
*   **Input:** Product image OR product URL OR custom script.
*   **Output:** 2–5 minute landscape video (16:9) for YouTube or VSLs.
*   **Process:** Similar to Mode 2, but utilizes a longer script (5+ paragraphs), slower pacing, and YouTube-optimized subtitle positioning.
*   **Cost:** 25 credits.

### Mode 4: UGC Avatar Ad Generator
*   **Input:** Product image + optional custom script.
*   **Output:** 30–60 second UGC-style video featuring a talking AI avatar.
*   **Process:** The Audio API generates the voiceover. The Video API (e.g., MuseTalk) lip-syncs a selected avatar to the audio. The MPT engine stitches the avatar track with B-roll cutaways.
*   **Cost:** 20 credits.

### Mode 5: Faceless Channel Automation
*   **Input:** Topic or keyword.
*   **Output:** Fully automated video with stock footage, AI voiceover, subtitles, and background music.
*   **Process:** The default MPT pipeline, utilizing stock footage APIs (e.g., Pexels) for rapid, high-volume content creation.
*   **Cost:** 8 credits.

---

## 4. Technical Architecture (The 5 Layers)

The platform is composed of five independent layers communicating via REST APIs and a job queue. This architecture ensures high availability and optimal cost-to-quality ratios through dynamic model selection.

### Layer 1: Frontend (User Dashboard)
*   **Tech Stack:** Next.js (App Router), TailwindCSS, shadcn/ui, NextAuth.js.
*   **Responsibilities:** User authentication, multi-tenant workspace management, credit balance display, generation wizard (inputs and human-in-the-loop controls), asset library, and Stripe billing portal. Hosted on Vercel.

### Layer 2: Multi-Model Orchestration API (The Brain)
*   **Tech Stack:** Node.js / FastAPI.
*   **Responsibilities:** Receives generation requests, validates JWT tokens and credit balances, and dynamically routes requests to Layer 2.5. It manages the business logic for each of the 5 Agent Modes and enqueues the final assets to Layer 3.

### Layer 2.5: Dynamic Model Router
*   **Responsibilities:** Acts as an intelligent switchboard. It selects the best API for a given task based on user requirements (speed vs. quality), cost parameters, and real-time availability (fallback routing).
*   **Supported Modalities (5+ APIs each):**
    *   **Video Generation:** Veo 3.1, Kling, Wan2.1, Runway Gen-3, Luma Dream Machine.
    *   **Image Generation:** NanoBanana Pro, Midjourney v6, DALL-E 3, Stable Diffusion 3, Flux.1.
    *   **Audio/Voice:** ElevenLabs, OpenAI TTS, PlayHT, Murf.ai, Azure Neural TTS.
    *   **LLM/Scripting:** GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 Pro, Llama 3, Mistral Large.

### Layer 3: Rendering Engine (Forked MoneyPrinterTurbo)
*   **Tech Stack:** Python, FastAPI, FFmpeg, MoviePy.
*   **Responsibilities:** This is the modified MPT codebase running on a dedicated GPU server (e.g., RunPod). It receives pre-generated assets (audio, video clips, subtitles) from Layer 2 and executes the heavy computational task of assembling the final MP4. It is completely decoupled from user or credit logic.

### Layer 4: Database & Storage
*   **Tech Stack:** PostgreSQL (Neon Serverless), Redis, Cloudflare R2 / AWS S3.
*   **Responsibilities:** Neon handles all relational data (tenants, users, credit ledgers, generation logs). Redis manages the job queue and real-time progress state. Cloudflare R2 stores all generated images and videos.

---

## 5. MoneyPrinterTurbo Fork Strategy

To transform MPT into the VisualAI Rendering Engine, we will fork the repository and surgically modify specific components while retaining its robust FFmpeg assembly logic.

1.  **Modify Visual Sourcing (`material.py`):** Rip out the hardcoded Pexels/Pixabay API integrations. Replace them with endpoints that accept pre-generated Veo 3.1 clips or NanoBanana images passed down from the Orchestration API.
2.  **Modify Script Generation (`llm.py`):** Replace generic "faceless video" prompts with product-specific, mode-aware prompts (e.g., direct-response copywriting frameworks for short ads).
3.  **Modify Voice Generation (`voice.py`):** Extend the existing Azure/Edge TTS integrations to support premium APIs like ElevenLabs and PlayHT, driven by the Model Router.
4.  **Modify Data Models (`schema.py`):** Extend the core `VideoParams` model to accept `user_id`, `tenant_id`, `mode`, and `product_id` to ensure proper tracking and asset association.
5.  **Add Authentication (`video.py` controllers):** Implement middleware to validate JWT tokens and verify credit balances before accepting a render job.

---

## 6. Multi-Tenant Database Schema (Neon PostgreSQL)

The database is designed to support marketing agencies managing multiple brands.

*   **`tenants`:** `id`, `name`, `plan`, `billing_id` (Stripe), `created_at`.
*   **`users`:** `id`, `tenant_id`, `email`, `role` (Admin/Editor/Viewer), `created_at`.
*   **`credit_balances`:** `user_id`, `tenant_id`, `balance`, `updated_at`.
*   **`credit_transactions`:** `id`, `user_id`, `amount`, `type` (hold/debit/credit), `reason`, `created_at`.
*   **`products`:** `id`, `user_id`, `tenant_id`, `name`, `image_url`, `description`, `created_at` (Brand Library).
*   **`generations`:** `id`, `user_id`, `tenant_id`, `product_id`, `mode`, `status`, `credits_used`, `output_url`.
*   **`assets`:** `id`, `generation_id`, `user_id`, `type` (image/video), `url`.
*   **`avatars`:** `id`, `name`, `preview_url`, `gender`, `language`, `is_premium` (System library for Mode 4).
*   **`voices`:** `id`, `elevenlabs_id`, `name`, `language`, `gender`, `preview_url` (System voice library).
*   **`social_connections`:** `id`, `user_id`, `platform` (tiktok/instagram), `access_token`, `expires_at`.

### Credit System Logic
1.  User initiates generation. System checks `credit_balances`.
2.  If sufficient, insert a `hold` transaction. Job is queued.
3.  On success, convert `hold` to `debit`. On failure, reverse the `hold`.
4.  Stripe webhooks trigger `credit` transactions to top-up balances.

---

## 7. UI/UX Specification (Cursor-Ready)

The UI must strictly adhere to the NexCognit brand identity, utilizing a dark, professional theme with high-contrast neon accents to represent cutting-edge AI.

### 7.1 Color Palette (Tailwind Configuration)

Add these to your `tailwind.config.js`:

```javascript
theme: {
  extend: {
    colors: {
      nex: {
        navy: '#0A1631',       // Primary background (from NexCognit header/stats bar)
        dark: '#050B18',       // Deep background for sidebar
        card: '#111D3D',       // Elevated card background
        neon: '#FFF86B',       // Primary CTA Yellow/Lime (from NexCognit "Talk To me" button)
        neonHover: '#E6DF60',  // Darker shade for CTA hover state
        blue: '#3462FA',       // Secondary accent blue
        textMain: '#FFFFFF',   // Primary text
        textMuted: '#A0AABF',  // Secondary text / subtitles
        border: '#1E2C52'      // Subtle borders between sections
      }
    },
    fontFamily: {
      heading: ['Syne', 'sans-serif'], // Main heading font from NexCognit
      sans: ['Inter', 'sans-serif']    // Clean UI font for dashboard data
    }
  }
}
```

### 7.2 Layout Architecture

The application utilizes a classic SaaS dashboard layout with a fixed left sidebar and a scrollable main content area.

#### Left Sidebar (Fixed)
*   **Background:** `bg-nex-dark`
*   **Width:** `w-64`
*   **Logo:** NexCognit logo at the top left.
*   **Navigation Links (Lucide Icons):**
    *   Dashboard (Home icon)
    *   My Assets (Folder icon)
    *   Brand Library (Briefcase icon)
    *   Billing & Credits (Credit Card icon)
*   **Bottom Element:** User profile snippet with current Credit Balance prominently displayed (e.g., "Credits: 1,250").

#### Main Content Area
*   **Background:** `bg-nex-navy`
*   **Padding:** `p-8`

### 7.3 The "Agent Modes" Dashboard (Core View)

The central dashboard presents the user with the 5 Agent Modes.

**Heading:** `<h1 className="font-heading text-3xl text-nex-textMain mb-6">What are you making today?</h1>`

**Grid Layout:** `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6`

**Mode Cards (The 5 Products):**
Each card must be a large, clickable area (`bg-nex-card border border-nex-border rounded-xl overflow-hidden hover:border-nex-neon transition-colors cursor-pointer`).

1.  **Product Shoot Generator:** Thumbnail showing a raw image turning into a studio shot.
2.  **Short Marketing Video:** Thumbnail showing a vertical 9:16 TikTok-style ad.
3.  **Long-Form Video:** Thumbnail showing a 16:9 YouTube review style.
4.  **UGC Avatar Ad:** Thumbnail showing a human-like AI avatar holding a product.
5.  **Faceless Channel Automation:** Thumbnail showing stock footage with bold captions.

### 7.4 The Creation Wizard (Step-by-Step UI)

When a user clicks a Mode Card, they enter the Creation Wizard. This must be a clean, step-by-step flow with a persistent progress indicator.

#### Step 1: Input Selection
Use a horizontal row of pill-shaped buttons to let the user choose their input method.
*   **Pills:** [ Upload Image ] [ Paste URL ] [ Write Script ]
*   **Active State:** `bg-nex-neon text-black`
*   **Inactive State:** `bg-nex-card text-nex-textMain border border-nex-border`

#### Step 2: The Multi-Model Router
Display a horizontal scrolling bar or a clean dropdown showing which AI models are active for this generation.
*   **UI Element:** Small badges/tags (e.g., `[ NanoBanana Pro ]`, `[ Veo 3.1 ]`, `[ ElevenLabs ]`).
*   **User Control:** Allow advanced users to click a badge to override the default model (e.g., switch Veo 3.1 to Kling).

#### Step 3: Human-in-the-Loop Controls
A form area where users can review and edit:
*   **Script Editor:** A large `textarea` pre-filled by the LLM.
*   **Voice Selector:** A custom select component with a "Play" icon to preview ElevenLabs voices.
*   **Music Selector:** Options to select background track or "No Music".

#### Step 4: Generation & Progress
When the user clicks the primary CTA (`bg-nex-neon text-black font-bold`), show a detailed progress state.
*   **Requirement:** A clear, interactive progress bar with status text (e.g., "1. Generating Script... 2. Rendering B-Roll... 3. Assembling Video...").
*   **Requirement:** Do not block the user from navigating away; show a minimized progress toast if they go back to the dashboard.

### 7.5 Asset Library (Media Management)

All generated content lives in a consolidated Media Library.
*   **Requirement:** Do not separate videos and images into different menu items. Use one unified "My Assets" view.
*   **Layout:** A masonry grid or standard grid of thumbnails.
*   **Actions:** Hovering over an asset reveals buttons to [ Download ], [ Copy Link ], or [ Publish to Social ].

### 7.6 Implementation Notes for Cursor/v0

*   **Components:** Use `shadcn/ui` for all base components (Buttons, Inputs, Dialogs, Selects, Progress bars) to ensure accessibility and rapid development.
*   **Styling:** Strictly use Tailwind classes with the custom `nex-` color tokens defined above. Avoid inline styles.
*   **Responsiveness:** Ensure the dashboard grid collapses to a single column on mobile, and the sidebar converts to a hamburger menu.
*   **Icons:** Use Lucide React icons. NEVER use emojis.

---

## 8. Pricing Strategy

VisualAI's credit-based pricing is benchmarked against competitors but offers significantly more value through the full pipeline and white-label capability.

| Plan | Price | Credits | Videos/Month | Best For |
|---|---|---|---|---|
| **Free** | $0 | 20 (one-time) | ~2 short videos | Testing |
| **Starter** | $29/month | 300 | ~30 short videos | Solo creators |
| **Growth** | $79/month | 1,000 | ~100 short videos | Small brands |
| **Pro** | $199/month | 3,000 | ~300 short videos | Agencies |
| **API Pro** | $299/month | 2,000 | N/A | SaaS builders |

---

## 9. MVP Roadmap (16 Weeks to Market)

**Phase 1 (Weeks 1–8): Core Functionality**
1.  Fork MoneyPrinterTurbo and implement API modifications (`material.py`, `schema.py`).
2.  Build Layer 2 Orchestration API with basic routing (NanoBanana, Veo 3.1, ElevenLabs, GPT-4o).
3.  Build Next.js Frontend with NextAuth (email/Google) and Stripe billing integration.
4.  Implement Neon PostgreSQL database and credit ledger logic.
5.  Launch Mode 1 (Product Shoot) and Mode 2 (Short Video).
6.  Deploy real-time progress tracking and asset library.

**Phase 2 (Weeks 9–16): Advanced Modes & Scaling**
1.  Launch Mode 3 (Long-Form Video) and Mode 5 (Faceless Channel).
2.  Integrate MuseTalk for Mode 4 (UGC Avatar Ad).
3.  Implement Brand Library (saving product assets and visual memory).
4.  Implement automated social media publishing (TikTok/Instagram APIs).
5.  Roll out Agency White-Label features (custom domains, sub-tenants).

**Phase 1 Success Metrics:**
- 100 paying users within 30 days of launch.
- Average 3+ generations per user per week.
- Net Promoter Score > 50.
- Churn rate < 5% monthly.
