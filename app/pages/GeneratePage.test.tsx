import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type ClassView, type MaterialView } from "../lib/api";
import { GeneratePage } from "./GeneratePage";

const classItem: ClassView = {
  id: "class-1",
  name: "國三班",
  grade: "國三",
  material_name: "自訂教材",
  weekly_schedule: "週三",
  objectives: ["閱讀"],
  overall_level: "中等",
  learned_content: "",
  common_errors: ["轉折詞"],
  teaching_preferences: "",
  homework_days: 4,
  homework_minutes: 30,
  notes: "",
  students: [],
  created_at: "2026-08-08T00:00:00Z",
  updated_at: "2026-08-08T00:00:00Z",
};
const material: MaterialView = {
  id: "material-1",
  display_name: "demo.md",
  media_type: "text/markdown",
  size_bytes: 100,
  grade: "國三",
  chapter: "Unit 1",
  topic: "Evidence",
  difficulty: "中等",
  tags: ["閱讀"],
  parse_status: "ready",
  extracted_text: "Text",
  parse_error: null,
  chunks: [],
  created_at: "2026-08-08T00:00:00Z",
};

function renderPage() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <GeneratePage token="token" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("GeneratePage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("walks through the wizard and submits normalized settings", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "classes").mockResolvedValue([classItem]);
    vi.spyOn(api, "materials").mockResolvedValue([material]);
    const create = vi.spyOn(api, "createGeneration").mockResolvedValue({
      id: "run-1",
      lesson_package_id: null,
      status: "queued",
      progress: 0,
      progress_message: "等待中",
      attempt_count: 0,
      failure_reason: null,
      provider: "mock",
      model: "qwen3:8b",
      prompt_version: "v1",
      duration_ms: null,
      token_usage: null,
      validation_summary: null,
      created_at: "2026-08-08T00:00:00Z",
    });
    renderPage();
    await user.selectOptions(await screen.findByLabelText("班級"), "class-1");
    await user.click(screen.getByLabelText("選擇教材 demo.md"));
    await user.click(screen.getByRole("button", { name: /下一步/ }));
    expect(screen.getByText("設定本次課程")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /下一步/ }));
    expect(screen.getByText("調整難度與課程結構")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /下一步/ }));
    await user.click(screen.getByRole("button", { name: /開始產生教材/ }));
    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][1]).toMatchObject({
      class_id: "class-1",
      material_ids: ["material-1"],
      lesson_minutes: 120,
      homework_days: 4,
    });
  });
});
