import type { AppModule } from "@/lib/api";
import { jobConfig } from "./job";
import { studyConfig } from "./study";
import type { ModuleConfig } from "./types";
import { visaConfig } from "./visa";

// The config of each module with applications.
export const MODULE_CONFIGS: Record<AppModule, ModuleConfig> = {
  study: studyConfig,
  job: jobConfig,
  visa: visaConfig,
};

export function configOf(module: AppModule): ModuleConfig {
  return MODULE_CONFIGS[module];
}
