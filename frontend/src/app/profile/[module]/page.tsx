import { Suspense } from "react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import ProfileView from "@/components/profile/ProfileView";
import { MODULES, type Module } from "@/lib/api";

export const metadata: Metadata = { title: "My profile" };

// One page per module, built ahead of time.
export function generateStaticParams() {
  return MODULES.map((module) => ({ module }));
}

// params is read inside <Suspense>, as Cache Components requires.
export default function ModuleProfilePage({ params }: PageProps<"/profile/[module]">) {
  return (
    <Suspense fallback={<p className="wrap">Loading…</p>}>
      {params.then(({ module }) => {
        if (!(MODULES as readonly string[]).includes(module)) notFound();
        return <ProfileView module={module as Module} />;
      })}
    </Suspense>
  );
}
