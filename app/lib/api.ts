import type { components } from "./api-types";

export type CurrentUser = components["schemas"]["CurrentUser"];
type StudentView = Omit<components["schemas"]["StudentView"], "weaknesses"> & {
  weaknesses: string[];
};
export type ClassView = Omit<
  components["schemas"]["ClassView"],
  "students" | "objectives" | "common_errors"
> & {
  students: StudentView[];
  objectives: string[];
  common_errors: string[];
};
export type ClassCreate = components["schemas"]["ClassCreate"];
export type StudentCreate = components["schemas"]["StudentCreate"];
export type MaterialView = Omit<
  components["schemas"]["MaterialView"],
  "tags" | "chunks"
> & {
  tags: string[];
  chunks: components["schemas"]["MaterialChunkView"][];
};
type Question = Omit<components["schemas"]["Question"], "options"> & {
  options: string[];
};
export type LessonBlock = Omit<
  components["schemas"]["LessonBlock"],
  "questions" | "source_references"
> & {
  questions: Question[];
  source_references: components["schemas"]["SourceReference"][];
};
export type PackageView = Omit<
  components["schemas"]["PackageView"],
  "blocks" | "objectives" | "validation_issues"
> & {
  blocks: LessonBlock[];
  objectives: string[];
  validation_issues: components["schemas"]["ValidationIssue"][];
};
export type GenerationRequest = components["schemas"]["GenerationRequest"];
export type GenerationRun = components["schemas"]["GenerationRunView"];
export type MemberView = components["schemas"]["MemberView"];
export type MemberCreate = components["schemas"]["MemberCreate"];
export type VersionView = components["schemas"]["VersionView"];

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

function detailMessage(payload: unknown): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) =>
          item && typeof item === "object" && "msg" in item
            ? String((item as { msg: unknown }).msg)
            : "輸入資料有誤",
        )
        .join("；");
    }
  }
  return "系統暫時無法完成操作，請稍後再試。";
}

export async function apiFetch<T>(
  path: string,
  token?: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    throw new ApiError(detailMessage(payload), response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  login: (email: string, password: string) =>
    apiFetch<{ access_token: string; user: CurrentUser }>(
      "/api/auth/login",
      undefined,
      {
        method: "POST",
        body: JSON.stringify({ email, password }),
      },
    ),
  me: (token: string) => apiFetch<CurrentUser>("/api/auth/me", token),
  classes: (token: string) => apiFetch<ClassView[]>("/api/classes", token),
  class: (token: string, id: string) =>
    apiFetch<ClassView>(`/api/classes/${id}`, token),
  createClass: (token: string, payload: ClassCreate) =>
    apiFetch<ClassView>("/api/classes", token, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  createStudent: (token: string, classId: string, payload: StudentCreate) =>
    apiFetch<StudentView>(`/api/classes/${classId}/students`, token, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  createOrganization: (token: string, name: string) =>
    apiFetch<{ access_token: string; user: CurrentUser }>(
      "/api/organizations",
      token,
      { method: "POST", body: JSON.stringify({ name }) },
    ),
  materials: (token: string) =>
    apiFetch<MaterialView[]>("/api/materials", token),
  material: (token: string, id: string) =>
    apiFetch<MaterialView>(`/api/materials/${id}`, token),
  uploadMaterial: (token: string, data: FormData) =>
    apiFetch<MaterialView>("/api/materials", token, {
      method: "POST",
      body: data,
    }),
  deleteMaterial: (token: string, id: string) =>
    apiFetch<void>(`/api/materials/${id}`, token, { method: "DELETE" }),
  packages: (token: string) => apiFetch<PackageView[]>("/api/packages", token),
  package: (token: string, id: string) =>
    apiFetch<PackageView>(`/api/packages/${id}`, token),
  createGeneration: (token: string, payload: GenerationRequest) =>
    apiFetch<GenerationRun>("/api/generation", token, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  generation: (token: string, id: string) =>
    apiFetch<GenerationRun>(`/api/generation/${id}`, token),
  retryGeneration: (token: string, id: string) =>
    apiFetch<GenerationRun>(`/api/generation/${id}/retry`, token, {
      method: "POST",
    }),
  updateBlock: (
    token: string,
    packageId: string,
    blockId: string,
    payload: Partial<LessonBlock>,
  ) =>
    apiFetch<PackageView>(
      `/api/packages/${packageId}/blocks/${blockId}`,
      token,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    ),
  blockAction: (
    token: string,
    packageId: string,
    blockId: string,
    action: "lock" | "regenerate" | "copy",
  ) =>
    apiFetch<PackageView>(
      `/api/packages/${packageId}/blocks/${blockId}/${action}`,
      token,
      { method: "POST" },
    ),
  moveBlock: (
    token: string,
    packageId: string,
    blockId: string,
    direction: "up" | "down",
  ) =>
    apiFetch<PackageView>(
      `/api/packages/${packageId}/blocks/${blockId}/move`,
      token,
      {
        method: "POST",
        body: JSON.stringify({ direction }),
      },
    ),
  deleteBlock: (token: string, packageId: string, blockId: string) =>
    apiFetch<PackageView>(
      `/api/packages/${packageId}/blocks/${blockId}`,
      token,
      { method: "DELETE" },
    ),
  approve: (token: string, packageId: string) =>
    apiFetch<PackageView>(`/api/packages/${packageId}/approve`, token, {
      method: "POST",
    }),
  submitReview: (token: string, packageId: string) =>
    apiFetch<PackageView>(`/api/packages/${packageId}/submit-review`, token, {
      method: "POST",
    }),
  versions: (token: string, packageId: string) =>
    apiFetch<VersionView[]>(`/api/packages/${packageId}/versions`, token),
  restore: (token: string, packageId: string, versionId: string) =>
    apiFetch<PackageView>(
      `/api/packages/${packageId}/versions/${versionId}/restore`,
      token,
      { method: "POST" },
    ),
  members: (token: string) =>
    apiFetch<MemberView[]>("/api/organizations/current/members", token),
  createMember: (token: string, payload: MemberCreate) =>
    apiFetch<MemberView>("/api/organizations/current/members", token, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  aiSettings: (token: string) =>
    apiFetch<Record<string, unknown>>("/api/settings/ai", token),
};

export async function fetchPreview(
  token: string,
  packageId: string,
  variant: string,
): Promise<string> {
  const response = await fetch(
    `${API_BASE}/api/packages/${packageId}/preview/${variant}`,
    {
      headers: { Authorization: `Bearer ${token}` },
    },
  );
  if (!response.ok) throw new ApiError("無法載入預覽", response.status);
  return response.text();
}

export async function downloadExport(
  token: string,
  packageId: string,
  variant: string,
  format: string,
) {
  const response = await fetch(
    `${API_BASE}/api/packages/${packageId}/export/${variant}.${format}`,
    {
      headers: { Authorization: `Bearer ${token}` },
    },
  );
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as unknown;
    throw new ApiError(detailMessage(payload), response.status);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `lessonforge-${variant}.${format}`;
  anchor.click();
  URL.revokeObjectURL(url);
}
