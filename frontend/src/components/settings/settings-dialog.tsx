// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  AlertTriangle,
  Cpu,
  Eye,
  EyeOff,
  HardDrive,
  Loader2,
  RotateCw,
} from "lucide-react";

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
// import { ModelSourceDialog } from "@/components/settings/model-source-dialog";
import { cn } from "@/lib/utils";
import {
  useModelGatewayConfig,
  useCatalogModels,
  useModelFeatures,
  useFeatureBindings,
  useSaveNewApiConnection,
  useTestNewApiConnection,
  useTestFeatureModel,
  useSyncCatalogModels,
  useSaveFeatureBindings,
  useUpdateModelCapabilities,
  useSaveMediaRelayConfig,
  type ModelCapability,
} from "@/lib/queries/model-gateway";
import {
  useSettingsStore,
  type AliyunOssStorageConfig,
  type CloudinaryStorageConfig,
  type MediaStorageProvider,
} from "@/stores/settingsStore";

interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const MEDIA_STORAGE_PROVIDERS: MediaStorageProvider[] = ["aliyun_oss", "cloudinary"];

// Codex 本地桥接暂时隐藏（保留组件代码，后端就绪后改回 true 即可恢复）。
const SHOW_CODEX_BRIDGE = false;

export function SettingsDialog({ open, onOpenChange }: SettingsDialogProps) {
  const { t } = useTranslation();
  const [page, setPage] = useState<"models" | "storage">("models");
  const statusQuery = useModelGatewayConfig(open);
  const settingsStatus = statusQuery.data?.data;
  const modelConfigured = Boolean(
    settingsStatus?.sources?.some((source) => source.configured),
  );
  const mediaStorageConfigured = Boolean(settingsStatus?.mediaRelay?.configured);

  const pageStatus = (configured: boolean, label: string) => {
    if (statusQuery.isLoading) {
      return (
        <Loader2
          className="absolute top-1 right-1 size-3 animate-spin text-muted-foreground sm:static sm:ml-auto sm:size-3.5"
          aria-hidden
        />
      );
    }
    if (configured) {
      return (
        <span
          className="absolute top-1 right-1 size-2 shrink-0 rounded-full bg-emerald-400 sm:static sm:ml-auto"
          aria-label={t("settings.statusConfigured", { page: label })}
          title={t("settings.statusConfigured", { page: label })}
        />
      );
    }
    return (
      <AlertTriangle
        className="absolute top-1 right-1 size-3.5 shrink-0 text-amber-400 sm:static sm:ml-auto sm:size-4"
        aria-label={t("settings.statusNotConfigured", { page: label })}
      />
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton
        className="flex h-[min(82vh,760px)] max-w-[calc(100%-2rem)] flex-col gap-0 overflow-hidden rounded-lg border border-border bg-black p-0 ring-0 sm:max-w-[1120px]"
      >
        <DialogHeader className="border-b border-border px-5 py-4">
          <DialogTitle>{t("settings.title")}</DialogTitle>
        </DialogHeader>

        <div className="flex min-h-0 flex-1">
          <nav
            aria-label={t("settings.navigationLabel")}
            className="flex w-14 shrink-0 flex-col gap-1 border-r border-border px-2 py-4 sm:w-44 sm:px-3"
          >
            <button
              type="button"
              aria-current={page === "models" ? "page" : undefined}
              onClick={() => setPage("models")}
              className={cn(
                "relative flex h-10 items-center justify-center gap-2 rounded-md px-2 text-sm font-medium transition-colors sm:justify-start sm:px-3",
                page === "models"
                  ? "bg-white/[0.09] text-foreground"
                  : "text-muted-foreground hover:bg-white/[0.05] hover:text-foreground",
              )}
            >
              <Cpu className="size-4" aria-hidden />
              <span className="hidden sm:inline">{t("settings.pages.models")}</span>
              {pageStatus(modelConfigured, t("settings.pages.models"))}
            </button>
            <button
              type="button"
              aria-current={page === "storage" ? "page" : undefined}
              onClick={() => setPage("storage")}
              className={cn(
                "relative flex h-10 items-center justify-center gap-2 rounded-md px-2 text-sm font-medium transition-colors sm:justify-start sm:px-3",
                page === "storage"
                  ? "bg-white/[0.09] text-foreground"
                  : "text-muted-foreground hover:bg-white/[0.05] hover:text-foreground",
              )}
            >
              <HardDrive className="size-4" aria-hidden />
              <span className="hidden sm:inline">{t("settings.pages.storage")}</span>
              {pageStatus(mediaStorageConfigured, t("settings.pages.storage"))}
            </button>
          </nav>

          {page === "models" ? (
            <div className="min-w-0 flex-1">
            <ScrollArea className="h-full [&_[data-slot=scroll-area-scrollbar]]:!w-1 [&_[data-slot=scroll-area-scrollbar]]:!border-l-0 [&_[data-slot=scroll-area-scrollbar]]:!p-0">
              <ModelConfigSection open={open && page === "models"} />
              {SHOW_CODEX_BRIDGE && <CodexBridgeSection />}
            </ScrollArea>
            </div>
          ) : (
            <div className="min-w-0 flex-1">
            <ScrollArea className="h-full [&_[data-slot=scroll-area-scrollbar]]:!w-1 [&_[data-slot=scroll-area-scrollbar]]:!border-l-0 [&_[data-slot=scroll-area-scrollbar]]:!p-0">
              <MediaStorageSection />
            </ScrollArea>
            </div>
          )}
        </div>

        <div className="flex justify-end border-t border-border px-5 py-3.5">
          <DialogClose render={<Button variant="outline" size="sm" />}>
            {t("settings.close")}
          </DialogClose>
        </div>
      </DialogContent>
    </Dialog>
  );
}

async function getRequestErrorMessage(error: unknown, fallback: string): Promise<string> {
  const response = (error as { response?: Response } | null)?.response;
  if (response) {
    const body = await response.clone().json().catch(() => null);
    if (body && typeof body === "object") {
      const data = body as { detail?: unknown; error?: unknown; message?: unknown };
      for (const value of [data.detail, data.error, data.message]) {
        if (typeof value === "string" && value.trim()) return value.trim();
      }
    }
    const text = await response.clone().text().catch(() => "");
    if (text.trim()) return text.trim();
  }
  const message = (error as { message?: unknown } | null)?.message;
  return typeof message === "string" && message.trim() ? message.trim() : fallback;
}


function ModelConfigSection({ open }: { open: boolean }) {
  const configQuery = useModelGatewayConfig(open);
  const modelsQuery = useCatalogModels(open);
  const featuresQuery = useModelFeatures(open);
  const bindingsQuery = useFeatureBindings(open);
  const saveConnection = useSaveNewApiConnection();
  const testConnection = useTestNewApiConnection();
  const testFeature = useTestFeatureModel();
  const syncModels = useSyncCatalogModels();
  const saveBindings = useSaveFeatureBindings();
  const updateCapabilities = useUpdateModelCapabilities();
  const config = configQuery.data?.data;
  const models = modelsQuery.data?.data.models ?? [];
  const features = featuresQuery.data?.data.features ?? [];
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [bindings, setBindings] = useState<Record<string, string>>({});

  useEffect(() => {
    if (config?.connection?.baseUrl) setBaseUrl(config.connection.baseUrl);
  }, [config?.connection?.baseUrl]);
  useEffect(() => {
    if (bindingsQuery.data?.data.bindings) setBindings(bindingsQuery.data.data.bindings);
  }, [bindingsQuery.data?.data.bindings]);

  const handleSaveConnection = async () => {
    if (!baseUrl.trim()) return toast.error("请输入 NewAPI 地址");
    const response = await saveConnection.mutateAsync({
      baseUrl: baseUrl.trim(),
      ...(apiKey.trim() ? { apiKey: apiKey.trim() } : {}),
    });
    if (!response.ok) return toast.error(response.error);
    setApiKey("");
    toast.success("NewAPI 配置已保存");
  };
  const handleTest = async () => {
    const response = await testConnection.mutateAsync();
    if (!response.ok) return toast.error(response.error);
    toast.success(`连接成功，发现 ${response.data.modelCount} 个模型`);
  };
  const handleSync = async () => {
    const response = await syncModels.mutateAsync();
    if (!response.ok) return toast.error(response.error);
    toast.success(`已同步 ${response.data.models.length} 个模型`);
  };
  const handleSaveBindings = async () => {
    const response = await saveBindings.mutateAsync(bindings);
    if (!response.ok) return toast.error(response.error);
    toast.success("全局功能模型已保存，所有项目立即共用");
  };
  const handleTestFeature = async (featureId: string) => {
    const saved = await saveBindings.mutateAsync(bindings);
    if (!saved.ok) return toast.error(saved.error);
    const response = await testFeature.mutateAsync(featureId);
    if (!response.ok) return toast.error(response.error);
    toast.success(response.data.liveRequest ? "模型请求测试成功" : "模型绑定验证成功");
  };
  const toggleCapability = (modelId: string, current: ModelCapability[], capability: ModelCapability) => {
    const next = current.includes(capability)
      ? current.filter((item) => item !== capability)
      : [...current.filter((item) => item !== "unknown"), capability];
    updateCapabilities.mutate({ modelId, capabilities: next.length ? next : ["unknown"] });
  };

  const pending = saveConnection.isPending || testConnection.isPending || syncModels.isPending;
  const status = config?.catalogStatus;
  const capabilities: ModelCapability[] = ["llm", "vision_llm", "image", "video", "audio", "embedding", "unknown"];
  const sourceNames = new Map(
    (config?.sources ?? []).map((source) => [source.id, source.name]),
  );
  const modelLabel = (model: (typeof models)[number]) =>
    `${model.id} [${sourceNames.get(model.sourceId) ?? model.sourceId}]`;

  return (
    <section className="px-5 py-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className={cn("size-1.5 rounded-full", config?.sources?.some((source) => source.configured) ? "bg-emerald-400" : "bg-amber-400")} />
          <h3 className="font-heading text-sm font-medium text-foreground">模型服务</h3>
        </div>
        {/* 暂时隐藏模型源管理入口。
        <ModelSourceDialog
          trigger={<Button size="sm" variant="outline">管理模型源</Button>}
        /> */}
      </div>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
        NewAPI 是默认模型源。保存配置并同步模型后，下方列表会自动刷新。
      </p>

      <div className="mt-4 space-y-3 rounded-lg border border-border/70 bg-white/[0.02] p-4">
        <div className="space-y-1.5">
          <Label htmlFor="newapi-base-url">NewAPI 地址</Label>
          <Input id="newapi-base-url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://newapi.example.com/v1" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="newapi-api-key">API Key</Label>
          <Input id="newapi-api-key" type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={config?.connection?.apiKeyPreview || "sk-..."} />
          <p className="text-[11px] text-muted-foreground">留空会保留已保存的 Key，不会覆盖。</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={handleSaveConnection} disabled={pending}>保存连接</Button>
          <Button size="sm" variant="outline" onClick={handleTest} disabled={pending || !config?.connection?.configured}>测试连接</Button>
          <Button size="sm" variant="outline" onClick={handleSync} disabled={pending || !config?.connection?.configured}>
            {syncModels.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <RotateCw className="size-3.5" />}同步模型
          </Button>
        </div>
        <div className="space-y-0.5 text-[11px] text-muted-foreground">
          {status?.lastTestAt ? <p>最近测试：{new Date(status.lastTestAt).toLocaleString()}</p> : null}
          {status?.lastSyncAt ? <p>最近同步：{new Date(status.lastSyncAt).toLocaleString()}</p> : null}
          {status?.lastError ? <p className="text-destructive">最近错误：{status.lastError}</p> : null}
          {status?.runtimeState === "ready" ? (
            <p className="text-emerald-400">知识库模型配置已热更新，无需重启后端。</p>
          ) : null}
          {status?.runtimeState === "pending" || status?.runtimeState === "draining" || status?.runtimeState === "applying" ? (
            <p className="text-amber-400">当前知识库任务完成后将自动应用最新模型配置。</p>
          ) : null}
          {status?.runtimeState === "failed" ? (
            <p className="text-destructive">知识库模型热更新失败：{status.lastReloadError || "请检查模型配置"}</p>
          ) : null}
          <p className="text-amber-400">更换 Embedding 模型或向量维度后，已有知识库必须显式重建；仅更换地址或 Key 无需重建。</p>
        </div>
        <a className="inline-flex text-xs text-primary underline underline-offset-4" href={config?.officialServiceUrl || "https://newapi.chonghuayunke.com"} target="_blank" rel="noreferrer">
          {config?.officialServiceLabel || "没有可用的 NewAPI 服务？获取官方服务"}
        </a>
      </div>

      <div className="mt-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h4 className="text-xs font-medium text-foreground">全局功能模型</h4>
            <p className="mt-1 text-[11px] text-muted-foreground">推荐分组按能力筛选；“全部模型”包含 unknown，可手动跨类型选择。</p>
          </div>
          <Button size="sm" onClick={handleSaveBindings} disabled={saveBindings.isPending || features.length === 0}>保存全部绑定</Button>
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {features.map((feature) => {
            const selected = bindings[feature.id] ?? "";
            const selectedModel = models.find((model) => model.bindingId === selected);
            const recommended = models.filter((model) => model.available && model.capabilities.includes(feature.capability));
            const mismatch = selectedModel && !selectedModel.capabilities.includes(feature.capability) && !selectedModel.capabilities.includes("unknown");
            return (
              <div key={feature.id} className="rounded-md border border-border/60 p-3">
                <div className="flex items-center justify-between gap-2">
                  <Label htmlFor={`feature-${feature.id}`}>{feature.label}</Label>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-muted-foreground">{feature.capability}</span>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-6 px-2 text-[10px]"
                      disabled={!selected || testFeature.isPending || saveBindings.isPending}
                      onClick={() => handleTestFeature(feature.id)}
                    >
                      测试
                    </Button>
                  </div>
                </div>
                <select
                  id={`feature-${feature.id}`}
                  className="mt-2 h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
                  value={selected}
                  onChange={(event) => setBindings((current) => ({ ...current, [feature.id]: event.target.value }))}
                >
                  <option value="">不选择</option>
                  <optgroup label="推荐模型">
                    {recommended.map((model) => <option key={`recommended-${model.bindingId}`} value={model.bindingId}>{modelLabel(model)}</option>)}
                  </optgroup>
                  <optgroup label="全部模型">
                    {models.map((model) => <option key={`all-${model.bindingId}`} value={model.bindingId}>{modelLabel(model)}{model.available ? "" : "（不可用）"}</option>)}
                  </optgroup>
                </select>
                {!selected && feature.required ? <p className="mt-1 text-[10px] text-amber-400">必需功能尚未配置</p> : null}
                {selectedModel && !selectedModel.available ? <p className="mt-1 text-[10px] text-destructive">所选模型已从上游消失</p> : null}
                {mismatch ? <p className="mt-1 text-[10px] text-amber-400">能力类型不匹配，仍允许手动保存</p> : null}
              </div>
            );
          })}
        </div>
      </div>

      {models.length > 0 ? (
        <details className="mt-5 rounded-lg border border-border/70 p-3">
          <summary className="cursor-pointer text-xs font-medium">手动标注模型能力（{models.length}）</summary>
          <div className="mt-3 max-h-72 space-y-2 overflow-auto">
            {models.map((model) => (
              <div key={model.bindingId} className="rounded border border-border/50 p-2">
                <p className="truncate text-xs text-foreground" title={modelLabel(model)}>{modelLabel(model)}</p>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {capabilities.map((capability) => (
                    <button key={capability} type="button" onClick={() => toggleCapability(model.bindingId, model.capabilities, capability)} className={cn("rounded border px-1.5 py-0.5 text-[10px]", model.capabilities.includes(capability) ? "border-primary bg-primary/15 text-primary" : "border-border text-muted-foreground")}>{capability}</button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </section>
  );
}
function MediaStorageSection() {
  const { t } = useTranslation();
  const configQuery = useModelGatewayConfig(true);
  const mediaRelay = configQuery.data?.data.mediaRelay;
  const mediaStorage = useSettingsStore((s) => s.mediaStorage);
  const setProvider = useSettingsStore((s) => s.setMediaStorageProvider);
  const updateCloudinary = useSettingsStore((s) => s.updateCloudinaryStorageConfig);
  const updateAliyunOss = useSettingsStore((s) => s.updateAliyunOssStorageConfig);
  const saveMediaRelay = useSaveMediaRelayConfig();

  const { provider, cloudinary, aliyunOss } = mediaStorage;
  const [ttlSeconds, setTtlSeconds] = useState("1800");
  const mediaRelayKey = JSON.stringify(mediaRelay ?? {});
  useEffect(() => {
    if (!mediaRelay) return;
    if (mediaRelay.provider === "aliyun_oss" || mediaRelay.provider === "cloudinary") {
      setProvider(mediaRelay.provider as MediaStorageProvider);
    }
    if (mediaRelay.endpoint || mediaRelay.bucket) {
      updateAliyunOss({
        endpoint: mediaRelay.endpoint || aliyunOss.endpoint,
        bucket: mediaRelay.bucket || aliyunOss.bucket,
        ...(mediaRelay.configured ? { accessKeyId: "", accessKeySecret: "" } : {}),
      });
    }
    if (mediaRelay.cloudName || mediaRelay.apiFolder) {
      updateCloudinary({
        cloudName: mediaRelay.cloudName || cloudinary.cloudName,
        apiFolder: mediaRelay.apiFolder || cloudinary.apiFolder,
        ...(mediaRelay.provider === "cloudinary" && mediaRelay.configured
          ? { apiKey: "", apiSecret: "" }
          : {}),
      });
    }
    if (mediaRelay.ttlSeconds) {
      setTtlSeconds((current) =>
        current === String(mediaRelay.ttlSeconds) ? current : String(mediaRelay.ttlSeconds),
      );
    }
    // Full AccessKey values must never be kept after the backend has a saved config.
    // Users re-enter them only when creating/updating the OSS relay credentials.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mediaRelayKey]);

  const hasConfiguredMediaRelay = Boolean(mediaRelay?.configured);
  const configuredProvider = hasConfiguredMediaRelay ? mediaRelay?.provider : provider;
  const handleSave = async () => {
    const ttl = Number(ttlSeconds.trim() || "0");
    if (!Number.isFinite(ttl) || ttl <= 0) {
      toast.error(t("settings.mediaStorage.validation.ttlSeconds"));
      return;
    }
    try {
      const res = await saveMediaRelay.mutateAsync(
        provider === "cloudinary"
          ? {
              provider: "cloudinary",
              ttlSeconds: Math.trunc(ttl),
              cloudName: cloudinary.cloudName.trim(),
              apiKey: cloudinary.apiKey.trim(),
              apiSecret: cloudinary.apiSecret.trim(),
              apiFolder: cloudinary.apiFolder.trim(),
            }
          : {
              provider: "aliyun_oss",
              ttlSeconds: Math.trunc(ttl),
              endpoint: aliyunOss.endpoint.trim(),
              bucket: aliyunOss.bucket.trim(),
              accessKeyId: aliyunOss.accessKeyId.trim(),
              accessKeySecret: aliyunOss.accessKeySecret.trim(),
            },
      );
      if (!res.ok) {
        toast.error(res.error);
        return;
      }
      if (provider === "cloudinary") {
        updateCloudinary({ apiKey: "", apiSecret: "" });
      } else {
        updateAliyunOss({ accessKeyId: "", accessKeySecret: "" });
      }
      toast.success(
        provider === "cloudinary"
          ? t("settings.mediaStorage.cloudinarySaveSuccess")
          : t("settings.mediaStorage.saveSuccess"),
      );
    } catch (error) {
      toast.error(await getRequestErrorMessage(error, t("settings.mediaStorage.saveFailed")));
    }
  };

  return (
    <section className="px-5 py-5">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "size-1.5 rounded-full",
            hasConfiguredMediaRelay ? "bg-emerald-400" : "bg-amber-400",
          )}
        />
        <h3 className="font-heading text-sm font-medium text-foreground">
          {t("settings.mediaStorage.title")}
        </h3>
        {!hasConfiguredMediaRelay ? (
          <AlertTriangle
            className="size-3.5 text-amber-400"
            aria-label={t("settings.mediaStorage.warningIconLabel")}
          />
        ) : null}
        <span className="ml-1 rounded bg-white/[0.06] px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
          {t("settings.mediaStorage.currentPlan")}: {configuredProvider === "cloudinary"
            ? t("settings.mediaStorage.providerCloudinary")
            : t("settings.mediaStorage.providerAliyunOss")}
        </span>
      </div>

      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
        {t("settings.mediaStorage.description")}
      </p>

      <p className="mt-3 text-xs text-muted-foreground">
        {t("settings.mediaStorage.status")}: {" "}
        <span className={hasConfiguredMediaRelay ? "text-emerald-400" : "text-amber-300"}>
          {hasConfiguredMediaRelay
            ? t("settings.mediaStorage.configured")
            : t("settings.mediaStorage.notConfigured")}
        </span>
        {hasConfiguredMediaRelay && mediaRelay?.source ? (
          <span className="ml-2 text-[11px] text-muted-foreground/80">
            {t("settings.mediaStorage.source", { source: mediaRelay.source })}
          </span>
        ) : null}
      </p>
      {!hasConfiguredMediaRelay ? (
        <div className="mt-3 flex gap-2 rounded-md border border-amber-500/35 bg-amber-500/10 px-3 py-2 text-[11px] leading-relaxed text-amber-100">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-300" aria-hidden />
          <p>{t("settings.mediaStorage.notConfiguredImpact")}</p>
        </div>
      ) : null}

      <div className="mt-4 flex items-center gap-3">
        <span className="w-[64px] shrink-0 text-xs text-muted-foreground">
          {t("settings.mediaStorage.provider")}
        </span>
        <Tabs
          value={provider}
          onValueChange={(value) => setProvider(value as MediaStorageProvider)}
        >
          <TabsList>
            {MEDIA_STORAGE_PROVIDERS.map((p) => (
              <TabsTrigger key={p} value={p}>
                {p === "aliyun_oss"
                  ? t("settings.mediaStorage.providerAliyunOss")
                  : t("settings.mediaStorage.providerCloudinary")}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      <div className="mt-4 space-y-2.5">
        {provider === "cloudinary" ? (
          <CloudinaryFields
            config={cloudinary}
            onChange={updateCloudinary}
            apiKeyPreview={mediaRelay?.cloudinaryApiKeyPreview ?? ""}
            apiSecretPreview={mediaRelay?.cloudinaryApiSecretPreview ?? ""}
          />
        ) : (
          <AliyunOssFields
            config={aliyunOss}
            onChange={updateAliyunOss}
            ttlSeconds={ttlSeconds}
            onTtlSecondsChange={setTtlSeconds}
            accessKeyIdPreview={mediaRelay?.accessKeyIdPreview ?? ""}
            accessKeySecretPreview={mediaRelay?.accessKeySecretPreview ?? ""}
          />
        )}
      </div>

      <div className="mt-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            {provider === "cloudinary"
              ? (
                <>
                  {t("settings.mediaStorage.cloudinaryFieldsHint")}{" "}
                  <a
                    href="https://cloudinary.com/users/register/free"
                    target="_blank"
                    rel="noreferrer"
                    className="text-cyan-400 hover:text-cyan-300"
                  >
                    {t("settings.mediaStorage.cloudinaryRegisterLink")}
                  </a>
                </>
              )
              : t("settings.mediaStorage.fieldsHint")}
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          className="shrink-0"
          onClick={handleSave}
          disabled={saveMediaRelay.isPending || configQuery.isLoading}
        >
          {saveMediaRelay.isPending ? <Loader2 className="size-3.5 animate-spin" /> : null}
          {provider === "cloudinary"
            ? t("settings.mediaStorage.saveCloudinary")
            : t("settings.mediaStorage.save")}
        </Button>
      </div>
    </section>
  );
}

function CloudinaryFields({
  config,
  onChange,
  apiKeyPreview,
  apiSecretPreview,
}: {
  config: CloudinaryStorageConfig;
  onChange: (patch: Partial<CloudinaryStorageConfig>) => void;
  apiKeyPreview: string;
  apiSecretPreview: string;
}) {
  const { t } = useTranslation();
  return (
    <>
      <FieldRow
        label={t("settings.mediaStorage.fields.cloudName")}
        value={config.cloudName}
        onChange={(v) => onChange({ cloudName: v })}
      />
      <FieldRow
        secret
        name="cloudinary-api-key"
        label={t("settings.mediaStorage.fields.apiKey")}
        value={config.apiKey}
        onChange={(v) => onChange({ apiKey: v })}
        placeholder={apiKeyPreview || undefined}
        savedPreview={apiKeyPreview}
      />
      <FieldRow
        secret
        name="cloudinary-api-secret"
        label={t("settings.mediaStorage.fields.apiSecret")}
        value={config.apiSecret}
        onChange={(v) => onChange({ apiSecret: v })}
        placeholder={apiSecretPreview || undefined}
        savedPreview={apiSecretPreview}
      />
      <FieldRow
        label={t("settings.mediaStorage.fields.apiFolder")}
        value={config.apiFolder}
        onChange={(v) => onChange({ apiFolder: v })}
      />
    </>
  );
}

function AliyunOssFields({
  config,
  onChange,
  ttlSeconds,
  onTtlSecondsChange,
  accessKeyIdPreview,
  accessKeySecretPreview,
}: {
  config: AliyunOssStorageConfig;
  onChange: (patch: Partial<AliyunOssStorageConfig>) => void;
  ttlSeconds: string;
  onTtlSecondsChange: (value: string) => void;
  accessKeyIdPreview: string;
  accessKeySecretPreview: string;
}) {
  const { t } = useTranslation();
  return (
    <>
      <FieldRow
        name="aliyun-oss-access-key-id"
        label={t("settings.mediaStorage.fields.accessKeyId")}
        value={config.accessKeyId}
        onChange={(v) => onChange({ accessKeyId: v })}
        placeholder={accessKeyIdPreview || undefined}
        savedPreview={accessKeyIdPreview}
      />
      <FieldRow
        secret
        name="aliyun-oss-access-key-secret"
        label={t("settings.mediaStorage.fields.accessKeySecret")}
        value={config.accessKeySecret}
        onChange={(v) => onChange({ accessKeySecret: v })}
        placeholder={accessKeySecretPreview || undefined}
        savedPreview={accessKeySecretPreview}
      />
      <FieldRow
        label={t("settings.mediaStorage.fields.bucket")}
        value={config.bucket}
        onChange={(v) => onChange({ bucket: v })}
      />
      <FieldRow
        label={t("settings.mediaStorage.fields.endpoint")}
        value={config.endpoint}
        onChange={(v) => onChange({ endpoint: v })}
      />
      <FieldRow
        label={t("settings.mediaStorage.fields.ttlSeconds")}
        value={ttlSeconds}
        onChange={onTtlSecondsChange}
      />
    </>
  );
}

function FieldRow({
  label,
  value,
  onChange,
  secret = false,
  placeholder,
  name,
  autoComplete,
  savedPreview,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  secret?: boolean;
  placeholder?: string;
  name?: string;
  autoComplete?: string;
  savedPreview?: string;
}) {
  const { t } = useTranslation();
  const [revealed, setRevealed] = useState(false);
  useEffect(() => {
    if (!value) setRevealed(false);
  }, [value]);
  const hasSavedSecret = Boolean(savedPreview && !value);
  return (
    <div className="grid grid-cols-[120px_1fr] items-center gap-3">
      <Label className="justify-start text-[11px] font-normal tracking-wide text-muted-foreground uppercase">
        {label}
      </Label>
      <div className="relative">
        <Input
          name={name}
          autoComplete={autoComplete ?? (secret ? "new-password" : undefined)}
          type={secret && !revealed ? "password" : "text"}
          value={value}
          placeholder={
            hasSavedSecret
              ? t("settings.secretSavedPlaceholder", { preview: savedPreview })
              : placeholder
          }
          onChange={(e) => onChange(e.target.value)}
          className={cn(
            "h-9 rounded-md border-input/80 focus-visible:border-ring/70 focus-visible:ring-1 focus-visible:ring-ring/30",
            secret && value && "pr-9",
            hasSavedSecret && "pr-16",
          )}
        />
        {secret && value ? (
          <button
            type="button"
            onClick={() => setRevealed((r) => !r)}
            aria-label={
              revealed
                ? t("settings.mediaStorage.hideSecret")
                : t("settings.mediaStorage.showSecret")
            }
            className="absolute top-1/2 right-2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
          >
            {revealed ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </button>
        ) : hasSavedSecret ? (
          <span className="absolute top-1/2 right-2 -translate-y-1/2 rounded bg-emerald-400/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-400">
            {t("settings.secretSavedBadge")}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function CodexBridgeSection() {
  const { t } = useTranslation();
  return (
    <section className="px-5 py-5">
      <div className="flex items-center gap-2">
        <span className="size-1.5 rounded-full bg-emerald-400" />
        <h3 className="font-heading text-sm font-medium text-foreground">
          {t("settings.codexBridge.title")}
        </h3>
        <span className="rounded bg-white/[0.06] px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
          {t("settings.codexBridge.badge")}
        </span>
      </div>

      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
        {t("settings.codexBridge.description")}
      </p>

      <div className="mt-3 space-y-2 text-xs">
        <div className="flex items-center gap-3">
          <span className="w-[48px] shrink-0 text-muted-foreground">
            {t("settings.codexBridge.statusLabel")}
          </span>
          <span className="inline-flex items-center gap-1.5 text-emerald-400">
            <span className="size-1.5 rounded-full bg-emerald-400" />
            {t("settings.codexBridge.statusConnected")}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="w-[48px] shrink-0 text-muted-foreground">
            {t("settings.codexBridge.authLabel")}
          </span>
          <span className="text-foreground">{t("settings.codexBridge.authReady")}</span>
        </div>
      </div>
    </section>
  );
}
