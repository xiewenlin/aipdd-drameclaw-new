using System.Text.Json;
using Gulong.ShortDrama.Core;

var failures = new List<string>();

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
    var directory = new DirectoryInfo(AppContext.BaseDirectory);
    while (directory is not null && !File.Exists(Path.Combine(directory.FullName, "Gulong.ShortDrama.Desktop.csproj"))) directory = directory.Parent;
    True(directory is not null);
    var project = File.ReadAllText(Path.Combine(directory!.FullName, "Gulong.ShortDrama.Desktop.csproj"));
    True(project.Contains("<UseWPF>true</UseWPF>", StringComparison.Ordinal));
    True(!project.Contains("Electron", StringComparison.OrdinalIgnoreCase));
});

Console.WriteLine();
Console.WriteLine($"Tests: {5 - failures.Count} passed, {failures.Count} failed");
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
