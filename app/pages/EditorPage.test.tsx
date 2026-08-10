import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type PackageView } from "../lib/api";
import { EditorPage } from "./PackagesPage";

const packageData: PackageView = {
  id: "p1",
  class_id: "c1",
  title: "國三閱讀教材",
  lesson_date: "2026-08-12",
  status: "draft",
  current_version: 2,
  total_minutes: 120,
  objectives: ["閱讀"],
  blocks: [
    {
      id: "b1",
      type: "reading",
      title: "閱讀理解",
      duration_minutes: 120,
      instructions: "先閱讀",
      teacher_notes: "提示",
      student_content: "Text",
      locked: true,
      source_references: [],
      questions: [
        {
          id: "q1",
          type: "reading",
          prompt: "Main idea?",
          options: ["A", "B", "C"],
          answer: "A",
          explanation: "A",
          points: 1,
          multiple_answers: false,
          reading_reference: "chunk",
        },
      ],
    },
  ],
  homework_days: [],
  weekly_quiz: null,
  parent_report: null,
  validation_issues: [],
  created_at: "2026-08-08T00:00:00Z",
  updated_at: "2026-08-08T00:00:00Z",
};

describe("EditorPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows locked state and disables regeneration and save", async () => {
    vi.spyOn(api, "package").mockResolvedValue(packageData);
    vi.spyOn(api, "versions").mockResolvedValue([]);
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <MemoryRouter initialEntries={["/packages/p1"]}>
          <Routes>
            <Route
              path="/packages/:id"
              element={<EditorPage token="token" />}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByDisplayValue("閱讀理解")).toBeDisabled();
    expect(screen.getByRole("button", { name: "單獨重生" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "儲存區塊" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "解鎖區塊" })).toBeEnabled();
  });
});
