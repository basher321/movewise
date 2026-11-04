"use client";

import { useRouter } from "next/navigation";
import type { AppModule } from "@/lib/api";
import { configOf } from "../modules";
import AgentWidget from "./AgentWidget";

// The agent on /consultancy or /jobs: selecting a match opens its item page.
export function ModuleAgent({ module }: { module: AppModule }) {
  const router = useRouter();
  const config = configOf(module);
  return <AgentWidget module={module} config={config.agent} onSelect={(slug) => router.push(config.base + "/" + slug)} />;
}

export default function StudyAgent() {
  return <ModuleAgent module="study" />;
}
