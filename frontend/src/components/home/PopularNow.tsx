"use client";

import { useEffect, useState } from "react";
import { COUNTRY_FLAGS, listCourseGroups, listUniversities, listVacancies } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import Card from "../Card";
import { useSettings } from "../SettingsProvider";

type Pick = { key: string; href: string; icon: string; title: string; text: string };

// "Popular right now" on the Home page: real published courses, universities and jobs.
// The whole section is hidden while there is nothing real to show.
export default function PopularNow() {
  const { licence } = useSettings();
  const [picks, setPicks] = useState<Pick[]>([]);

  useEffect(() => {
    if (!licence) return;
    let live = true;
    const tasks: Promise<Pick[]>[] = [];
    if (licence.modules.course) {
      tasks.push(
        listCourseGroups().then((groups) =>
          groups
            .flatMap((g) => g.courses)
            .slice(0, 2)
            .map((c) => ({ key: "c" + c.id, href: "/courses/" + c.slug, icon: c.icon || "📚", title: c.title, text: formatMoney(c.price_poisha) + (c.duration ? " · " + c.duration : "") })),
        ),
      );
    }
    if (licence.modules.study) {
      tasks.push(
        listUniversities().then((list) =>
          list.slice(0, 2).map((u) => ({ key: "u" + u.id, href: "/consultancy/" + u.slug, icon: COUNTRY_FLAGS[u.country] ?? "🎓", title: u.name, text: u.country + " · " + u.fields.slice(0, 2).join(", ") })),
        ),
      );
    }
    if (licence.modules.job) {
      tasks.push(
        listVacancies().then((list) =>
          list.slice(0, 2).map((v) => ({ key: "v" + v.id, href: "/jobs/" + v.slug, icon: COUNTRY_FLAGS[v.country] ?? "🛂", title: v.title, text: v.employer + " · " + v.country })),
        ),
      );
    }
    void Promise.allSettled(tasks).then((results) => {
      if (!live) return;
      setPicks(results.flatMap((r) => (r.status === "fulfilled" ? r.value : [])).slice(0, 4));
    });
    return () => {
      live = false;
    };
  }, [licence]);

  if (!picks.length) return null;

  return (
    <section>
      <div className="wrap">
        <div className="head">
          <h2>Popular right now</h2>
        </div>
        <div className="grid">
          {picks.map((p) => (
            <Card key={p.key} href={p.href}>
              <div className="ico">{p.icon}</div>
              <h3>{p.title}</h3>
              <p>{p.text}</p>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}
