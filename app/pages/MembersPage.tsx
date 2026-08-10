"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, CirclePlus, ShieldCheck, UserRound } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { api, type CurrentUser, type MemberCreate } from "../lib/api";
import {
  Button,
  Card,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Modal,
  Notice,
  PageHeader,
} from "../components/ui";

const memberSchema = z.object({
  email: z.email("請輸入有效 Email"),
  display_name: z.string().min(2, "請輸入姓名"),
  password: z.string().min(10, "密碼至少 10 個字元"),
  role: z.enum(["owner", "admin", "teacher"]),
});
type MemberForm = z.infer<typeof memberSchema>;

export function MembersPage({
  token,
  currentUser,
  onTokenChange,
}: {
  token: string;
  currentUser: CurrentUser;
  onTokenChange: (token: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [organizationOpen, setOrganizationOpen] = useState(false);
  const [organizationName, setOrganizationName] = useState("");
  const [organizationError, setOrganizationError] = useState("");
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["members"],
    queryFn: () => api.members(token),
  });
  const canManage =
    currentUser.role === "owner" || currentUser.role === "admin";
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<MemberForm>({
    resolver: zodResolver(memberSchema),
    defaultValues: { role: "teacher", password: "LocalTeacher!2026" },
  });
  const mutation = useMutation({
    mutationFn: (payload: MemberCreate) => api.createMember(token, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["members"] });
      reset();
      setOpen(false);
    },
    onError: (error) =>
      setError("root", {
        message: error instanceof Error ? error.message : "新增成員失敗",
      }),
  });
  const organizationMutation = useMutation({
    mutationFn: () => api.createOrganization(token, organizationName),
    onSuccess: (result) => onTokenChange(result.access_token),
    onError: (error) =>
      setOrganizationError(
        error instanceof Error ? error.message : "建立組織失敗",
      ),
  });
  if (query.isLoading) return <LoadingState label="載入組織成員…" />;
  if (query.error)
    return (
      <ErrorState
        message={
          query.error instanceof Error ? query.error.message : "無法載入成員"
        }
      />
    );
  return (
    <div className="page-stack">
      <PageHeader
        title="組織與成員"
        description="Owner、admin 與 teacher 權限都由組織 membership 管理。"
        actions={
          <div className="button-row">
            <Button
              variant="secondary"
              onClick={() => setOrganizationOpen(true)}
            >
              <Building2 />
              建立新補習班
            </Button>
            {canManage ? (
              <Button onClick={() => setOpen(true)}>
                <CirclePlus />
                建立教師帳號
              </Button>
            ) : null}
          </div>
        }
      />
      {!canManage ? (
        <Notice>
          Teacher 角色可查看組織成員，但只有 owner 或 admin 可以新增帳號。
        </Notice>
      ) : null}
      <Card>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>成員</th>
                <th>Email</th>
                <th>角色</th>
                <th>權限說明</th>
              </tr>
            </thead>
            <tbody>
              {query.data?.map((member) => (
                <tr key={member.id}>
                  <td>
                    <div className="member-cell">
                      <div className="user-avatar">
                        <UserRound />
                      </div>
                      <strong>{member.display_name}</strong>
                    </div>
                  </td>
                  <td>{member.email}</td>
                  <td>
                    <span className="role-pill">
                      <ShieldCheck />
                      {member.role}
                    </span>
                  </td>
                  <td>
                    {member.role === "owner"
                      ? "完整管理與組織設定"
                      : member.role === "admin"
                        ? "成員與內容管理"
                        : "班級、教材與生成操作"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Modal
        open={open}
        onOpenChange={setOpen}
        title="建立教師帳號"
        description="此密碼只供本機 Demo；正式環境請要求使用者首次登入後更換。"
      >
        <form
          className="modal-form"
          onSubmit={handleSubmit((values) => mutation.mutate(values))}
        >
          {errors.root?.message ? (
            <Notice kind="error">{errors.root.message}</Notice>
          ) : null}
          <Field label="顯示名稱" error={errors.display_name?.message}>
            <Input {...register("display_name")} />
          </Field>
          <Field label="Email" error={errors.email?.message}>
            <Input type="email" {...register("email")} />
          </Field>
          <Field label="初始密碼" error={errors.password?.message}>
            <Input type="password" {...register("password")} />
          </Field>
          <Field label="角色">
            <select className="input" {...register("role")}>
              <option value="teacher">teacher</option>
              <option value="admin">admin</option>
              <option value="owner">owner</option>
            </select>
          </Field>
          <div className="modal-actions">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setOpen(false)}
            >
              取消
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "建立中…" : "建立成員"}
            </Button>
          </div>
        </form>
      </Modal>
      <Modal
        open={organizationOpen}
        onOpenChange={setOrganizationOpen}
        title="建立新補習班"
        description="建立後會立即切換到新的組織，所有班級、教材與教材包皆與原組織隔離。"
      >
        <form
          className="modal-form"
          onSubmit={(event) => {
            event.preventDefault();
            setOrganizationError("");
            if (organizationName.trim().length < 2) {
              setOrganizationError("組織名稱至少需要 2 個字元");
              return;
            }
            organizationMutation.mutate();
          }}
        >
          {organizationError ? (
            <Notice kind="error">{organizationError}</Notice>
          ) : null}
          <Field label="補習班名稱">
            <Input
              value={organizationName}
              onChange={(event) => setOrganizationName(event.target.value)}
              placeholder="例：晨光英文學苑"
            />
          </Field>
          <div className="modal-actions">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setOrganizationOpen(false)}
            >
              取消
            </Button>
            <Button type="submit" disabled={organizationMutation.isPending}>
              {organizationMutation.isPending ? "建立中…" : "建立並切換"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
