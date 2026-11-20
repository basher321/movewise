// B28: rules of the CV Agent wizard.

import { describe, expect, it } from "vitest";
import type { CvMissingField, CvProject } from "@/lib/api";
import { chunk, exportName, furthestStep, leftBlank, linesOf, progress, splitList, unanswered } from "../wizard";

const project = (changes: Partial<CvProject>): CvProject => ({
  id: "1", module: "job", title: "", cv_type: null, cover_letter: false, country: null, category: null, job_advert_text: "",
  doc_kinds: [], consent: false, template: null, page_length: 2, step: 1, status: "draft", created_at: "", updated_at: "", ...changes,
});

const field = (key: string, required = true, value: unknown = null): CvMissingField => ({
  key, label: key, kind: "text", section: "personal", required, options: [], value, hint: "", note: "",
});

describe("CV wizard", () => {
  it("shows at most 6 questions per screen", () => {
    expect(chunk([1, 2, 3, 4, 5, 6, 7, 8]).map((c) => c.length)).toEqual([6, 2]);
    expect(chunk([])).toEqual([]);
  });

  it("cannot skip ahead of what is filled in", () => {
    expect(furthestStep(project({}))).toBe(1);
    expect(furthestStep(project({ cv_type: "new", step: 7 }))).toBe(2);
    expect(furthestStep(project({ cv_type: "new", country: "UK", category: "it", step: 2 }))).toBe(4);
    expect(furthestStep(project({ cv_type: "new", country: "UK", category: "it", step: 7 }))).toBe(7);
    expect(progress(4)).toBe(50);
  });

  it("finds required answers that are still empty", () => {
    const fields = [field("a"), field("b", false), field("c", true, ["x"]), field("d")];
    expect(unanswered(fields, { d: "  " }).map((f) => f.key)).toEqual(["a", "d"]);
    expect(unanswered(fields, { a: "ok", d: "ok" })).toEqual([]);
  });

  it("names downloads like the server", () => {
    expect(exportName("Md. Rahim  Uddin", "Germany", "cv", "pdf")).toBe("Rahim_Uddin_CV_Germany.pdf");
    expect(exportName("Md. Rafiul Karim (Rafi)", "Australia", "cv", "pdf")).toBe("Rafiul_Karim_CV_Australia.pdf");
    expect(exportName("José Núñez", "New Zealand", "letter", "docx")).toBe("Jose_Nunez_Cover_Letter_New_Zealand.docx");
    expect(exportName("", null, "cv", "pdf")).toBe("My_CV_International.pdf");
  });

  it("splits typed lists", () => {
    expect(splitList("Python, SQL; Python\nGit")).toEqual(["Python", "SQL", "Git"]);
    expect(linesOf("• Built X\n- Fixed Y\n\n")).toEqual(["Built X", "Fixed Y"]);
  });
});

describe("optional questions left blank", () => {
  it("are reported so that part is left out of the CV", () => {
    const fields = [field("training.new.name", false), field("training.new.date", false), field("personal.full_name"), field("x", false, ["a"])];
    expect(leftBlank(fields, { "training.new.date": "2024-05" })).toEqual(["training.new.name", "personal.full_name"]);
    expect(leftBlank(fields, { "training.new.name": "First aid", "training.new.date": "2024-05", "personal.full_name": "A" })).toEqual([]);
  });
});
