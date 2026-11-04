"use client";

import type { ReactNode } from "react";
import type { Module } from "@/lib/api";
import { isLicensed, useSettings } from "./SettingsProvider";

// Shows its children only when the module is licensed (nothing until the licence has loaded).
export default function IfLicensed({ module, children }: { module: Module; children: ReactNode }) {
  const { licence } = useSettings();
  return isLicensed(licence, module) ? children : null;
}
