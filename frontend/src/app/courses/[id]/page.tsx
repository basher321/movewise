import { Suspense } from "react";
import type { Metadata } from "next";
import CourseDetail from "@/components/course/CourseDetail";

// The item comes from the database for each request, so this route is rendered per request.
export const instant = false;

export const metadata: Metadata = { title: "Course" };

// [id] is the course slug. Courses come from the database, so the page is built per request
// and the course itself is read in the browser.
export default function CoursePage({ params }: PageProps<"/courses/[id]">) {
  return (
    <Suspense fallback={<p className="wrap">Loading…</p>}>
      {params.then(({ id }) => (
        <CourseDetail slug={id} />
      ))}
    </Suspense>
  );
}
