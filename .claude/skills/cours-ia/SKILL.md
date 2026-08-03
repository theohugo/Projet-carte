---
name: cours-ia
description: Panorama des outils IA (chatbots, image, vidéo, audio, musique, 3D, code, automatisation, compute) et annuaire de serveurs MCP (glama.ai) — référence de cours.
---

# IA

## Panorama des Outils IA

Tableau récapitulatif des principaux outils IA, classés par modalité et cas d'usage, avec éditeur, dernier modèle, statut, tarifs et point fort.

### Généralistes (chatbots / assistants IA)
- **ChatGPT** (OpenAI, GPT-5.5/o3) — ultra-polyvalent, écosystème mature, agentivité et exécution de code puissante.
- **Claude** (Anthropic, Opus 4.7/Sonnet 4.6) — finesse d'écriture, contexte massif (1M+ tokens), Artifacts pour la programmation.
- **Gemini** (Google) — intégration profonde Google (Docs, Drive, Gmail), recherche web temps réel.
- **Copilot** (Microsoft) — intégré Windows/Office.
- **Le Chat** (Mistral AI) — modèles européens open-weights, confidentialité stricte.
- **Grok** (xAI) — ton irrévérencieux, accès direct au flux X.
- **DeepSeek** — raisonnement mathématique/logique, rapport coût/performance imbattable.
- **Perplexity** — moteur de recherche assisté par IA, sourçage précis, « Deep Research ».

### Images
Midjourney (photoréalisme artistique), DALL-E (respect strict des prompts, intégré ChatGPT), Leonardo.Ai (assets design), Ideogram (texte dans l'image), Stable Diffusion (open-weights, ControlNet, local), Adobe Firefly (Photoshop/Illustrator), Flux (photoréalisme, open-source), Canva Dream Lab, Sandcastles.ai.

### Vidéo
Kling AI (physique/cohérence temporelle), Runway Gen-4.5 (contrôle caméra, VFX), Sora (séquences longues cinématographiques), HeyGen (avatars + lip-sync), Google Veo, Hailuo AI, Luma Dream Machine, Pika (effets ludiques), VEED (montage + sous-titres auto).

### Audio & TTS
ElevenLabs (clonage vocal, réalisme émotionnel), Google Cloud TTS, Microsoft Azure TTS, AWS Polly, OpenAI TTS, PlayHT, Sesame AI.

### Musique
Suno (chansons complètes, qualité radio), Udio, Stable Audio (instrumental/ambiance), MusicGen (Meta, open-source, local), AIVA (export MIDI), Riffusion (spectrogrammes).

### 3D
Meshy (modèles texturés PBR), Luma Genie, Tripo3D (topologie précise), CSM.ai (2D→3D), Spline AI (React/TS), Rodin (avatars + rigging).

### Recherche académique
NotebookLM (synthèse multi-sources ancrée), SciSpace, Consensus (études peer-reviewed), Elicit (revues de littérature), Scite.ai (Smart Citations), Humata AI.

### Code (développement / vibe coding)
Cursor (IDE agentique, Composer multi-fichiers), **Claude Code** (agent CLI, explore un dépôt, exécute des tests, gère Git en autonomie), AntiGravity (Vibe Coding, support natif MCP), GitHub Copilot, Windsurf (Codeium), OpenAI Codex.

### UI & Graphisme
Figma (standard UI/UX + wireframes IA), Canva Studio Magique, **v0.dev** (Vercel — prompt/screenshot → composants React/Tailwind/HTML), Galileo AI (fichiers Figma), Uizard (croquis → maquettes), Relume (sitemaps/wireframes → Figma).

### Automatisation
Zapier (+7000 apps), Make (Celonis, scénarios complexes), n8n (fair-code, Docker, nœuds LangChain), IFTTT (grand public/domotique), Dify (LLMOps open-source, RAG), Windmill (scripts → workflows).

### Compute & Inférence
Nebius (cloud IA européen, GPU H100/B200), Novita AI (inférence serverless), Hugging Face (hub central, Spaces/Inference Endpoints, Docker), AWS Bedrock/SageMaker, Azure AI Studio, Google Cloud Vertex AI, Groq (puces LPU, très haute vitesse).

### Recommandations d'usage
Choix selon le cas d'usage plutôt que classement absolu : polyvalence/écosystème (ChatGPT, Claude, Gemini) pour un usage quotidien ; coût/performance (DeepSeek) pour budgets serrés ; souveraineté/confidentialité (Mistral, solutions open-weights) pour contraintes réglementaires ou déploiement local ; outils spécialisés par modalité selon la qualité de rendu recherchée ; environnements de code de plus en plus **agentiques** (Cursor, Claude Code, AntiGravity, Windsurf). Le protocole **MCP** (Model Context Protocol) est cité comme standard émergent (AntiGravity nativement compatible).

**Lien :** https://modules.apti.space/outils/ia/ia

## Glama.ai — annuaire de serveurs MCP

### Qu'est-ce que le Model Context Protocol (MCP)
Protocole standardisé permettant aux assistants IA (comme Claude) de se connecter à des services, données et outils externes. Les « serveurs MCP » sont des passerelles reliant un modèle de langage à des applications tierces, API, bases de données ou systèmes de fichiers — capacités d'action (**tools**), d'accès à des données (**resources**) et de prompts prêts à l'emploi.

### Qu'est-ce que Glama.ai
Plateforme et **annuaire centralisé dédié au MCP** — un registre catalogant serveurs, connecteurs, outils et clients MCP publics (~67 600 serveurs référencés). Rôle similaire à un « app store »/registre de paquets pour l'écosystème MCP.

### À quoi ça sert
Découvrir/rechercher des serveurs par nom, fonction ou domaine ; filtrer par hébergement (Remote/Local/Hybrid), langage (Python/TypeScript), capacité exposée (Tools/Resources/Prompts) ou domaine (Developer Tools, Search, App Automation, Finance, Databases, Security, Web Scraping) ; inspecter un serveur ; comparer hébergement/tarifs.

### Exemples de serveurs listés
ThinAir Geo (géocodage/routage), @fouradata/mcp (web scraping), DataNexus MCP (données gouvernementales), Network Sketcher (diagrammes réseau), Reel Estate MCP (photos → vidéos immobilières), Argent (simulateurs iOS/émulateurs Android), ScrapeUnblocker (contournement anti-bot).

**Lien :** https://glama.ai/mcp/servers
