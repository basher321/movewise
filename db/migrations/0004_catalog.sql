-- 0004_catalog: course groups, courses, universities and vacancies.
-- The tables start empty; the super admin adds every item. Nothing is ever deleted:
-- items are hidden (published = false) or closed.

CREATE TABLE course_groups (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL CHECK (btrim(name) <> '' AND length(name) <= 80),
  description text NOT NULL DEFAULT '' CHECK (length(description) <= 300),
  sort_order integer NOT NULL DEFAULT 0,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX course_groups_active_sort_idx ON course_groups (active, sort_order);

CREATE TRIGGER trg_course_groups_updated_at BEFORE UPDATE ON course_groups
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE courses (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  group_id uuid NOT NULL REFERENCES course_groups (id) ON DELETE RESTRICT,
  title text NOT NULL CHECK (btrim(title) <> ''),
  icon text NOT NULL DEFAULT '',
  colour text NOT NULL CHECK (colour ~ '^#[0-9A-Fa-f]{6}$'),
  price_poisha bigint NOT NULL CHECK (price_poisha > 0),
  duration text NOT NULL DEFAULT '',
  level text NOT NULL DEFAULT '',
  description text NOT NULL DEFAULT '',
  learn_points text[] NOT NULL CHECK (cardinality(learn_points) > 0),
  syllabus text[] NOT NULL CHECK (cardinality(syllabus) > 0),
  published boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX courses_group_id_idx ON courses (group_id);
CREATE INDEX courses_published_idx ON courses (published);

CREATE TRIGGER trg_courses_updated_at BEFORE UPDATE ON courses
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE universities (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  name text NOT NULL CHECK (btrim(name) <> ''),
  country text NOT NULL CHECK (btrim(country) <> ''),
  city text NOT NULL DEFAULT '',
  levels text[] NOT NULL CHECK (cardinality(levels) > 0),
  fields text[] NOT NULL CHECK (cardinality(fields) > 0),
  tuition_usd integer NOT NULL CHECK (tuition_usd >= 0),
  min_gpa numeric(3,2) NOT NULL CHECK (min_gpa >= 0 AND min_gpa <= 4),
  min_ielts numeric(2,1) NOT NULL CHECK (min_ielts >= 0 AND min_ielts <= 9 AND (min_ielts * 2) = trunc(min_ielts * 2)),
  intakes text NOT NULL DEFAULT '',
  deadline_text text NOT NULL DEFAULT '',
  scholarships text NOT NULL DEFAULT '',
  work_rights text NOT NULL DEFAULT '',
  conditions text NOT NULL DEFAULT '',
  apply_link text NOT NULL DEFAULT '' CHECK (apply_link = '' OR apply_link LIKE 'https://%'),
  admissions_email text NOT NULL DEFAULT '',
  fee_override_poisha bigint CHECK (fee_override_poisha IS NULL OR fee_override_poisha > 0),
  published boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX universities_published_idx ON universities (published);

CREATE TRIGGER trg_universities_updated_at BEFORE UPDATE ON universities
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE vacancies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  title text NOT NULL CHECK (btrim(title) <> ''),
  employer text NOT NULL CHECK (btrim(employer) <> ''),
  country text NOT NULL CHECK (btrim(country) <> ''),
  occupation text NOT NULL CHECK (btrim(occupation) <> ''),
  min_experience integer NOT NULL CHECK (min_experience >= 0),
  min_education integer NOT NULL CHECK (min_education BETWEEN 0 AND 3),
  min_english integer NOT NULL CHECK (min_english BETWEEN 0 AND 2),
  salary_usd integer NOT NULL CHECK (salary_usd > 0),
  seats integer CHECK (seats IS NULL OR seats >= 1),
  apply_by date,
  contract text NOT NULL DEFAULT '',
  benefits text NOT NULL DEFAULT '',
  conditions text NOT NULL DEFAULT '',
  employer_licence text NOT NULL DEFAULT '',
  employer_email text NOT NULL DEFAULT '',
  employer_verified boolean NOT NULL DEFAULT false,
  closed boolean NOT NULL DEFAULT false,
  fee_override_poisha bigint CHECK (fee_override_poisha IS NULL OR fee_override_poisha > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX vacancies_open_idx ON vacancies (closed, employer_verified);

CREATE TRIGGER trg_vacancies_updated_at BEFORE UPDATE ON vacancies
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
