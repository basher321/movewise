import { describe, expect, it } from "vitest";
import type { AdminUser, LicenceView } from "../../api";
import { allowedTabs, resolveTab } from "../tabs";

const ALL: LicenceView = { holder: "Test", expires_at: null, active: true, modules: { course: true, study: true, job: true, visa: true } };
const STUDY_ONLY: LicenceView = { holder: "Test", expires_at: null, active: true, modules: { course: false, study: true, job: false, visa: false } };

const user = (role: AdminUser["role"], sections: AdminUser["sections"] = []): AdminUser => ({
  id: "ADM-1",
  name: "Test",
  email: "t@example.com",
  role,
  approved: true,
  active: true,
  sections,
  created_at: "2026-10-25T00:00:00.000Z",
});

const ids = (admin: AdminUser, licence: LicenceView) => allowedTabs(admin, licence).map((t) => t.id);

describe("admin tabs", () => {
  it("super_admin sees every tab, ending with Settings and Licence", () => {
    expect(ids(user("super_admin"), ALL)).toEqual(["course", "study", "job", "visa", "enq", "docs", "agents", "partners", "acc", "cat", "fees", "notifs", "team", "audit", "set", "lic"]);
  });

  it("admin sees only assigned licensed modules, then Enquiries, Documents, Notifications", () => {
    expect(ids(user("admin", ["study", "job"]), ALL)).toEqual(["study", "job", "enq", "docs", "agents", "partners", "notifs"]);
    expect(ids(user("admin", ["study", "job"]), STUDY_ONLY)).toEqual(["study", "enq", "docs", "agents", "partners", "notifs"]);
  });

  it("B16: the Agents tab needs a licensed study or job section", () => {
    expect(ids(user("admin", ["course"]), ALL)).not.toContain("agents");
    expect(ids(user("admin", ["job"]), STUDY_ONLY)).not.toContain("agents");
    expect(ids(user("super_admin"), { ...ALL, modules: { course: true, study: false, job: false, visa: false } })).not.toContain("agents");
  });

  it("B18: the Partners tab follows the person's licensed modules, course included", () => {
    expect(ids(user("admin", ["course"]), ALL)).toContain("partners");
    expect(ids(user("admin", ["course"]), STUDY_ONLY)).not.toContain("partners");
  });

  it("finance sees Accounts and Notifications only", () => {
    expect(ids(user("finance", ["course"]), ALL)).toEqual(["acc", "notifs"]);
  });

  it("labels and icons come from the reference", () => {
    const labels = allowedTabs(user("super_admin"), ALL).map((t) => t.label);
    expect(labels).toContain("🎓 Student Consultancy");
    expect(labels).toContain("⚙ Settings");
    expect(labels).toContain("🔑 Licence");
  });

  it("unlicensed modules drop out and a stale module tab falls back to the first allowed tab", () => {
    const tabs = allowedTabs(user("super_admin"), STUDY_ONLY);
    expect(tabs.map((t) => t.id)).not.toContain("course");
    expect(tabs.map((t) => t.id)).not.toContain("job");
    expect(resolveTab("course", tabs)).toBe("study");
    expect(resolveTab(null, tabs)).toBe("study");
    expect(resolveTab("acc", tabs)).toBe("acc");
  });

  it("Settings and Licence links are kept for anyone, so the screen can show FORBIDDEN", () => {
    const tabs = allowedTabs(user("admin", ["study"]), ALL);
    expect(resolveTab("set", tabs)).toBe("set");
    expect(resolveTab("lic", tabs)).toBe("lic");
  });
});

describe("B19 immigration tab", () => {
  it("an admin of the visa section sees Immigration, Agents and Partners", () => {
    expect(ids(user("admin", ["visa"]), ALL)).toEqual(["visa", "enq", "docs", "agents", "partners", "notifs"]);
  });

  it("is hidden when visa is not licensed", () => {
    expect(ids(user("admin", ["visa"]), STUDY_ONLY)).not.toContain("visa");
  });
});
