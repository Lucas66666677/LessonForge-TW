"use client";

import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from "@tanstack/react-query";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { Shell } from "./components/Shell";
import { ErrorState, LoadingState } from "./components/ui";
import { api } from "./lib/api";
import { ClassesPage, ClassDetailPage } from "./pages/ClassesPage";
import { DashboardPage } from "./pages/DashboardPage";
import { ExportsPage } from "./pages/ExportsPage";
import { GeneratePage, GenerationProgressPage } from "./pages/GeneratePage";
import { LoginPage } from "./pages/LoginPage";
import { MaterialDetailPage, MaterialsPage } from "./pages/MaterialsPage";
import { MembersPage } from "./pages/MembersPage";
import { EditorPage, PackagesPage } from "./pages/PackagesPage";
import { PreviewPage } from "./pages/PreviewPage";
import { SettingsPage } from "./pages/SettingsPage";

const subscribeToClientRuntime = () => () => undefined;
const getClientSnapshot = () => true;
const getServerSnapshot = () => false;

function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo({ left: 0, top: 0, behavior: "instant" });
  }, [pathname]);

  return null;
}

function AuthenticatedApp({
  token,
  logout,
  onTokenChange,
}: {
  token: string;
  logout: () => void;
  onTokenChange: (token: string) => void;
}) {
  const user = useQuery({
    queryKey: ["current-user", token],
    queryFn: () => api.me(token),
    retry: false,
  });
  if (user.isLoading)
    return (
      <div className="app-loading">
        <LoadingState label="開啟 LessonForge 工作台…" />
      </div>
    );
  if (user.error || !user.data)
    return (
      <div className="app-loading">
        <ErrorState
          message={
            user.error instanceof Error ? user.error.message : "登入憑證已失效"
          }
          retry={logout}
        />
      </div>
    );
  return (
    <Shell user={user.data} onLogout={logout}>
      <Routes>
        <Route path="/" element={<DashboardPage token={token} />} />
        <Route path="/classes" element={<ClassesPage token={token} />} />
        <Route
          path="/classes/:id"
          element={<ClassDetailPage token={token} />}
        />
        <Route path="/materials" element={<MaterialsPage token={token} />} />
        <Route
          path="/materials/:id"
          element={<MaterialDetailPage token={token} />}
        />
        <Route path="/generate" element={<GeneratePage token={token} />} />
        <Route
          path="/generation/:id"
          element={<GenerationProgressPage token={token} />}
        />
        <Route path="/packages" element={<PackagesPage token={token} />} />
        <Route path="/packages/:id" element={<EditorPage token={token} />} />
        <Route
          path="/packages/:id/preview"
          element={<PreviewPage token={token} />}
        />
        <Route path="/exports" element={<ExportsPage token={token} />} />
        <Route
          path="/members"
          element={
            <MembersPage
              token={token}
              currentUser={user.data}
              onTokenChange={onTokenChange}
            />
          }
        />
        <Route path="/settings" element={<SettingsPage token={token} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  );
}

export function LessonForgeApp() {
  const mounted = useSyncExternalStore(
    subscribeToClientRuntime,
    getClientSnapshot,
    getServerSnapshot,
  );
  const queryClient = useMemo(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 20_000, retry: 1 } },
      }),
    [],
  );
  const [token, setToken] = useState(() =>
    typeof window === "undefined"
      ? ""
      : (window.sessionStorage.getItem("lessonforge-token") ?? ""),
  );
  const login = (value: string) => {
    window.sessionStorage.setItem("lessonforge-token", value);
    setToken(value);
  };
  const logout = () => {
    window.sessionStorage.removeItem("lessonforge-token");
    queryClient.clear();
    setToken("");
  };

  if (!mounted) {
    return (
      <div className="app-loading">
        <LoadingState label="開啟 LessonForge 工作台…" />
      </div>
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ScrollToTop />
        {token ? (
          <AuthenticatedApp
            token={token}
            logout={logout}
            onTokenChange={login}
          />
        ) : (
          <LoginPage onLogin={login} />
        )}
      </BrowserRouter>
    </QueryClientProvider>
  );
}
