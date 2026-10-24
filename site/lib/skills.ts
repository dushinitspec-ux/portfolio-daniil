// Technology names are the same in every language, so they live here and not in messages/.
export const skillGroups = {
  ai: ["Claude Code", "OpenAI Codex", "LLM APIs", "Prompt design", "Structured outputs", "Automation"],
  web: ["Python", "FastAPI", "aiogram 3", "Telegram Bot API", "HTML / CSS", "JavaScript", "Git"],
  infra: ["MikroTik RouterOS", "LAN / Wi-Fi", "CCTV / NVR", "Access control", "IoT sensors", "Windows"],
} as const;

export type SkillGroup = keyof typeof skillGroups;
