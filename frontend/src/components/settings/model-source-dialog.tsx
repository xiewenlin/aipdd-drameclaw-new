// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useState, type ReactElement } from "react";
import { Loader2, Pencil, Plus, RotateCw, Trash2, Wifi } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  type ModelSource,
  type SaveModelSourceInput,
  useCatalogModels,
  useDeleteModelSource,
  useModelSources,
  useSaveModelSource,
  useSyncModelSource,
  useTestModelSource,
} from "@/lib/queries/model-gateway";

interface ModelSourceDialogProps {
  trigger: ReactElement;
}

async function getErrorMessage(error: unknown, fallback: string): Promise<string> {
  const response = (error as { response?: Response } | null)?.response;
  if (response) {
    const body = await response.clone().json().catch(() => null);
    if (body && typeof body === "object") {
      const data = body as { detail?: unknown; error?: unknown; message?: unknown };
      if (typeof data.detail === "string" && data.detail.trim()) return data.detail;
      if (data.detail && typeof data.detail === "object") {
        const message = (data.detail as { message?: unknown }).message;
        if (typeof message === "string" && message.trim()) return message;
      }
      if (typeof data.error === "string" && data.error.trim()) return data.error;
      if (typeof data.message === "string" && data.message.trim()) return data.message;
    }
  }
  const message = (error as { message?: unknown } | null)?.message;
  return typeof message === "string" && message.trim() ? message : fallback;
}

export function ModelSourceDialog({ trigger }: ModelSourceDialogProps) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<ModelSource | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");

  const sourcesQuery = useModelSources(open);
  const modelsQuery = useCatalogModels(open);
  const saveSource = useSaveModelSource();
  const deleteSource = useDeleteModelSource();
  const testSource = useTestModelSource();
  const syncSource = useSyncModelSource();
  const customSources = (sourcesQuery.data?.data.sources ?? []).filter(
    (source) => !source.isDefault,
  );
  const models = modelsQuery.data?.data.models ?? [];

  const resetForm = () => {
    setName("");
    setBaseUrl("");
    setApiKey("");
    setEditing(null);
    setShowForm(false);
  };

  const handleEdit = (source: ModelSource) => {
    setEditing(source);
    setName(source.name);
    setBaseUrl(source.baseUrl);
    setApiKey("");
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!name.trim()) return toast.error("请输入模型源名称");
    if (!baseUrl.trim()) return toast.error("请输入模型源地址");
    if (!editing && !apiKey.trim()) return toast.error("请输入 API Key");
    const input: SaveModelSourceInput = {
      ...(editing ? { id: editing.id } : {}),
      name: name.trim(),
      baseUrl: baseUrl.trim(),
      ...(apiKey.trim() ? { apiKey: apiKey.trim() } : {}),
    };
    try {
      const response = await saveSource.mutateAsync(input);
      if (!response.ok) return toast.error(response.error);
      try {
        const syncResponse = await syncSource.mutateAsync(response.data.id);
        if (!syncResponse.ok) {
          toast.warning("模型源已保存，但获取模型失败，请点击“获取模型”重试");
          resetForm();
          return;
        }
        const modelCount = syncResponse.data.models.filter(
          (model) => model.sourceId === response.data.id && model.available,
        ).length;
        toast.success(
          `${editing ? "模型源已更新" : "模型源已添加"}，已获取 ${modelCount} 个模型`,
        );
      } catch (error) {
        toast.warning(
          await getErrorMessage(error, "模型源已保存，但获取模型失败，请点击“获取模型”重试"),
        );
      }
      resetForm();
    } catch (error) {
      toast.error(await getErrorMessage(error, "保存模型源失败"));
    }
  };

  const handleDelete = async (source: ModelSource) => {
    if (!window.confirm(`删除模型源“${source.name}”？相关模型和功能绑定也会移除。`)) return;
    try {
      const response = await deleteSource.mutateAsync(source.id);
      if (!response.ok) return toast.error(response.error);
      toast.success("模型源已删除");
    } catch (error) {
      toast.error(await getErrorMessage(error, "删除模型源失败"));
    }
  };

  const handleTest = async (source: ModelSource) => {
    try {
      const response = await testSource.mutateAsync(source.id);
      if (!response.ok) return toast.error(response.error);
      toast.success(`连接成功，发现 ${response.data.modelCount} 个模型`);
    } catch (error) {
      toast.error(await getErrorMessage(error, "模型源连接失败"));
    }
  };

  const handleSync = async (source: ModelSource) => {
    try {
      const response = await syncSource.mutateAsync(source.id);
      if (!response.ok) return toast.error(response.error);
      const modelCount = response.data.models.filter(
        (model) => model.sourceId === source.id && model.available,
      ).length;
      toast.success(`已从“${source.name}”获取 ${modelCount} 个模型，下拉列表已刷新`);
    } catch (error) {
      toast.error(await getErrorMessage(error, "同步模型失败"));
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) resetForm();
      }}
    >
      <DialogTrigger render={trigger} />
      <DialogContent className="max-w-[640px] rounded-lg border border-border bg-black p-0">
        <DialogHeader className="border-b border-border px-5 py-4">
          <DialogTitle>模型源管理</DialogTitle>
        </DialogHeader>
        <div className="p-5">
          <p className="mb-4 text-xs leading-relaxed text-muted-foreground">
            添加 OpenAI 兼容直连源，例如火山引擎 Ark。地址会原样保留，因此可填写包含
            <code className="mx-1">/api/v3</code>
            的完整 API 根地址。保存后会自动连接平台并获取模型，获取成功后模型会立即出现在功能模型下拉列表中。
          </p>

          {!showForm ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowForm(true)}
              className="mb-4"
            >
              <Plus className="mr-1 size-3.5" />添加模型源
            </Button>
          ) : (
            <div className="mb-4 space-y-3 rounded-lg border border-border/70 bg-white/[0.02] p-4">
              <div className="space-y-1.5">
                <Label htmlFor="model-source-name">模型源名称</Label>
                <Input
                  id="model-source-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="例如：火山引擎"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="model-source-url">API 地址</Label>
                <Input
                  id="model-source-url"
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.target.value)}
                  placeholder="https://ark.cn-beijing.volces.com/api/v3"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="model-source-key">API Key</Label>
                <Input
                  id="model-source-key"
                  type="password"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder={editing?.apiKeyPreview || "sk-..."}
                />
                {editing ? (
                  <p className="text-[10px] text-muted-foreground">留空会保留已保存的 Key。</p>
                ) : null}
              </div>
              <div className="flex gap-2">
                <Button size="sm" onClick={handleSave} disabled={saveSource.isPending || syncSource.isPending}>
                  {saveSource.isPending || syncSource.isPending ? <Loader2 className="mr-1 size-3.5 animate-spin" /> : null}
                  {editing ? "更新并重新获取模型" : "保存并获取模型"}
                </Button>
                <Button size="sm" variant="ghost" onClick={resetForm}>取消</Button>
              </div>
            </div>
          )}

          <ScrollArea className="max-h-72">
            <div className="space-y-2">
              {sourcesQuery.isLoading ? (
                <div className="flex justify-center py-8"><Loader2 className="size-4 animate-spin" /></div>
              ) : null}
              {!sourcesQuery.isLoading && customSources.length === 0 ? (
                <p className="py-6 text-center text-xs text-muted-foreground">尚未添加直连模型源</p>
              ) : null}
              {customSources.map((source) => (
                <div key={source.id} className="rounded-md border border-border/60 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium text-foreground">{source.name}</p>
                      <p className="truncate text-[10px] text-muted-foreground">{source.baseUrl}</p>
                      <p className="mt-1 text-[10px] text-muted-foreground">{source.apiKeyPreview}</p>
                    </div>
                    <span className="shrink-0 rounded bg-emerald-400/10 px-2 py-1 text-[10px] text-emerald-400">
                      已获取 {models.filter((model) => model.sourceId === source.id && model.available).length} 个模型
                    </span>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <Button type="button" size="sm" variant="outline" onClick={() => handleTest(source)} disabled={testSource.isPending} className="h-7 px-2 text-[10px]">
                      <Wifi className="mr-1 size-3" />测试连接
                    </Button>
                    <Button type="button" size="sm" variant="outline" onClick={() => handleSync(source)} disabled={syncSource.isPending} className="h-7 px-2 text-[10px]">
                      {syncSource.isPending ? <Loader2 className="mr-1 size-3 animate-spin" /> : <RotateCw className="mr-1 size-3" />}获取模型
                    </Button>
                    <Button type="button" size="sm" variant="ghost" onClick={() => handleEdit(source)} className="h-7 px-2 text-[10px]">
                      <Pencil className="mr-1 size-3" />编辑配置
                    </Button>
                    <button type="button" title="删除模型源" onClick={() => handleDelete(source)} disabled={deleteSource.isPending} className="ml-auto rounded p-1.5 text-muted-foreground hover:bg-red-500/20 hover:text-red-400 disabled:opacity-50">
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        </div>
      </DialogContent>
    </Dialog>
  );
}
