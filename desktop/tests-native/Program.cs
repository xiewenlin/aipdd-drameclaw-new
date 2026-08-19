using System.Text.Json;
using Gulong.ShortDrama.Core;

var failures = new List<string>();
const int testCount = 10;

Run("builds the exact Gulong H3 native task contract", () =>
{
    var payload = TaskContracts.Build("  雨夜追车  ", 8, "9:16");
    using var json = JsonDocument.Parse(JsonSerializer.Serialize(payload));
    var root = json.RootElement;
    Equal("desktop_agent", root.GetProperty("source_channel").GetString());
    Equal("minimax_h3_shared", root.GetProperty("model").GetString());
    Equal("雨夜追车", root.GetProperty("prompt").GetString());
    Equal("9:16", root.GetProperty("aspect_ratio").GetString());
    Equal(8, root.GetProperty("duration_seconds").GetInt32());
    Equal("balanced", root.GetProperty("profile").GetString());
    Equal(0, root.GetProperty("assets").GetProperty("images").GetArrayLength());
});

Run("rejects invalid prompt and duration before a billable request", () =>
{
    Throws<ContractValidationException>(() => TaskContracts.Build("", 5, "9:16"));
    Throws<ContractValidationException>(() => TaskContracts.Build("镜头", 0, "9:16"));
    Throws<ContractValidationException>(() => TaskContracts.Build("镜头", 601, "9:16"));
});

Run("falls back to a safe aspect ratio", () =>
{
    Equal("9:16", TaskContracts.Build("镜头", 5, "javascript:").AspectRatio);
});

Run("uses unique native idempotency keys", () =>
{
    var first = TaskContracts.CreateIdempotencyKey();
    var second = TaskContracts.CreateIdempotencyKey();
    True(first.StartsWith("dramaclaw-native-", StringComparison.Ordinal));
    True(first != second);
});

Run("desktop project is WPF-native and has no Electron dependency", () =>
{
    var directory = FindDesktopRoot();
    var project = File.ReadAllText(Path.Combine(directory.FullName, "Gulong.ShortDrama.Desktop.csproj"));
    True(project.Contains("<UseWPF>true</UseWPF>", StringComparison.Ordinal));
    True(!project.Contains("Electron", StringComparison.OrdinalIgnoreCase));
});

Run("installer always compiles its Chinese script as UTF-8", () =>
{
    var buildScript = File.ReadAllText(Path.Combine(FindDesktopRoot().FullName, "build-native.ps1"));
    True(buildScript.Contains("\"/INPUTCHARSET\" \"UTF8\"", StringComparison.Ordinal));
});

Run("native window uses the compatible render path before account initialization", () =>
{
    var directory = FindDesktopRoot();
    var appSource = File.ReadAllText(Path.Combine(directory.FullName, "App.xaml.cs"));
    var windowSource = File.ReadAllText(Path.Combine(directory.FullName, "MainWindow.xaml.cs"));
    True(appSource.Contains("RenderOptions.ProcessRenderMode = RenderMode.SoftwareOnly", StringComparison.Ordinal));
    True(windowSource.Contains("ContentRendered += MainWindow_ContentRendered", StringComparison.Ordinal));
});

Run("native production workspace exposes the complete web workflow", () =>
{
    var directory = FindDesktopRoot();
    var xaml = File.ReadAllText(Path.Combine(directory.FullName, "ProductionWorkspace.xaml"));
    foreach (var stage in new[] { "项目管理", "文本导入", "视觉风格", "角色设定", "场景与道具", "分集规划", "剧本编辑", "节拍与分镜", "配音与音频", "视频生成", "合成与导出", "素材资产库", "自由画布", "AI 创作工具", "任务中心" })
        True(xaml.Contains($"Content=\"{stage}\"", StringComparison.Ordinal));
    True(!xaml.Contains("WebView2", StringComparison.OrdinalIgnoreCase));
});

Run("production API authenticates through Gulong SSO", () =>
{
    var directory = FindDesktopRoot();
    var official = File.ReadAllText(Path.Combine(directory.FullName, "Services", "OfficialApiClient.cs"));
    var production = File.ReadAllText(Path.Combine(directory.FullName, "Services", "DramaApiClient.cs"));
    True(official.Contains("/api/auth/short-drama-sso", StringComparison.Ordinal));
    True(production.Contains("/api/v1/auth/gulong/exchange", StringComparison.Ordinal));
    True(production.Contains("CookieContainer", StringComparison.Ordinal));
});

Run("account window is re-centered and initialization is single-flight", () =>
{
    var source = File.ReadAllText(Path.Combine(FindDesktopRoot().FullName, "AccountWebWindow.xaml.cs"));
    True(source.Contains("_initializationTask ??=", StringComparison.Ordinal));
    True(source.Contains("PlaceOverOwner();", StringComparison.Ordinal));
});

Console.WriteLine();
Console.WriteLine($"Tests: {testCount - failures.Count} passed, {failures.Count} failed");
if (failures.Count > 0)
{
    foreach (var failure in failures) Console.Error.WriteLine(failure);
    return 1;
}
return 0;

void Run(string name, Action test)
{
    try
    {
        test();
        Console.WriteLine($"PASS  {name}");
    }
    catch (Exception error)
    {
        failures.Add($"FAIL  {name}: {error.Message}");
    }
}

static void Equal<T>(T expected, T actual)
{
    if (!EqualityComparer<T>.Default.Equals(expected, actual)) throw new InvalidOperationException($"Expected {expected}, got {actual}");
}

static void True(bool condition)
{
    if (!condition) throw new InvalidOperationException("Expected true");
}

static void Throws<T>(Action action) where T : Exception
{
    try { action(); }
    catch (T) { return; }
    throw new InvalidOperationException($"Expected {typeof(T).Name}");
}

static DirectoryInfo FindDesktopRoot()
{
    var directory = new DirectoryInfo(AppContext.BaseDirectory);
    while (directory is not null && !File.Exists(Path.Combine(directory.FullName, "Gulong.ShortDrama.Desktop.csproj"))) directory = directory.Parent;
    return directory ?? throw new DirectoryNotFoundException("Desktop project root was not found");
}
