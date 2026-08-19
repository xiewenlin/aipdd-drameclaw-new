using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Windows;
using Microsoft.Web.WebView2.Core;

namespace Gulong.ShortDrama;

public enum AuthMode
{
    Login,
    Register,
}

public partial class AccountWebWindow : Window
{
    private static readonly Uri OfficialHome = new("https://sologle.com/");
    private bool _initialized;
    private Task? _initializationTask;
    private bool _allowClose;
    private bool _authFlow;

    public event EventHandler? ReturnedToWorkbench;

    public AccountWebWindow()
    {
        InitializeComponent();
    }

    public CoreWebView2 Browser => AccountBrowser.CoreWebView2;

    public Task InitializeBrowserAsync()
    {
        if (_initialized) return Task.CompletedTask;
        return _initializationTask ??= InitializeBrowserCoreAsync();
    }

    private async Task InitializeBrowserCoreAsync()
    {
        if (_initialized) return;

        try
        {
            var originalShowInTaskbar = ShowInTaskbar;
            var originalOpacity = Opacity;
            var originalLeft = Left;
            var originalTop = Top;
            ShowInTaskbar = false;
            Opacity = 0.01;
            WindowStartupLocation = WindowStartupLocation.Manual;
            Left = -20_000;
            Top = -20_000;
            Show();

            var dataDirectory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Gulong", "ShortDrama", "WebView2");
            Directory.CreateDirectory(dataDirectory);
            var environment = await CoreWebView2Environment.CreateAsync(userDataFolder: dataDirectory);
            await AccountBrowser.EnsureCoreWebView2Async(environment);
            AccountBrowser.CoreWebView2.Settings.AreDevToolsEnabled = false;
            AccountBrowser.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
            AccountBrowser.CoreWebView2.Settings.IsStatusBarEnabled = false;
            AccountBrowser.NavigationCompleted += (_, _) => LoadingPanel.Visibility = Visibility.Collapsed;
            AccountBrowser.CoreWebView2.NewWindowRequested += (_, args) =>
            {
                args.Handled = true;
                if (Uri.TryCreate(args.Uri, UriKind.Absolute, out var target) && IsOfficial(target))
                {
                    AccountBrowser.CoreWebView2.Navigate(target.ToString());
                    return;
                }
                if (Uri.TryCreate(args.Uri, UriKind.Absolute, out target) && target.Scheme == Uri.UriSchemeHttps)
                    Process.Start(new ProcessStartInfo(target.ToString()) { UseShellExecute = true });
            };

            AccountBrowser.CoreWebView2.Navigate(OfficialHome.ToString());
            _initialized = true;
            Hide();
            ShowInTaskbar = originalShowInTaskbar;
            Opacity = originalOpacity;
            Left = originalLeft;
            Top = originalTop;
            WindowStartupLocation = WindowStartupLocation.CenterOwner;
        }
        finally
        {
            if (!_initialized) _initializationTask = null;
        }
    }

    public async Task<bool> ShowAuthAsync(AuthMode mode)
    {
        await InitializeBrowserAsync();
        WindowHeading.Text = mode == AuthMode.Register ? "注册古龙账号" : "登录古龙账号";
        _authFlow = true;
        ShowInTaskbar = true;
        Opacity = 1;
        PlaceOverOwner();
        Show();
        Activate();
        try { await NavigateAndWaitAsync(OfficialHome); }
        catch (TimeoutException) { LoadingPanel.Visibility = Visibility.Collapsed; }

        var tabText = mode == AuthMode.Register ? "注册" : "登录";
        var script = $$"""
          (() => {
            const click = (selector, text) => {
              const nodes = [...document.querySelectorAll(selector)];
              const target = text ? nodes.find(node => node.textContent.trim() === text) : nodes[0];
              if (target) { target.click(); return true; }
              return false;
            };
            click('button.login-button');
            setTimeout(() => click('.account-tabs button', '{{tabText}}'), 150);
            return true;
          })()
          """;
        await AccountBrowser.ExecuteScriptAsync(script);

        while (_authFlow && IsVisible)
        {
            if (await BrowserHasAuthenticatedUserAsync())
            {
                _authFlow = false;
                Hide();
                return true;
            }
            await Task.Delay(800);
        }
        return false;
    }

    public async Task ShowOfficialPageAsync(string path, string title)
    {
        await InitializeBrowserAsync();
        _authFlow = false;
        WindowHeading.Text = title;
        ShowInTaskbar = true;
        Opacity = 1;
        PlaceOverOwner();
        Show();
        Activate();
        try { await NavigateAndWaitAsync(new Uri(OfficialHome, path)); }
        catch (TimeoutException) { LoadingPanel.Visibility = Visibility.Collapsed; }
    }

    public void ForceClose()
    {
        _allowClose = true;
        Close();
    }

    protected override void OnClosing(CancelEventArgs e)
    {
        if (!_allowClose)
        {
            e.Cancel = true;
            _authFlow = false;
            Hide();
            ReturnedToWorkbench?.Invoke(this, EventArgs.Empty);
            return;
        }
        base.OnClosing(e);
    }

    private async Task<bool> BrowserHasAuthenticatedUserAsync()
    {
        try
        {
            var result = await AccountBrowser.ExecuteScriptAsync("fetch('/api/auth/me',{credentials:'include'}).then(r=>r.json()).then(x=>Boolean(x&&x.user)).catch(()=>false)");
            return string.Equals(result, "true", StringComparison.OrdinalIgnoreCase);
        }
        catch (InvalidOperationException)
        {
            return false;
        }
    }

    private async Task NavigateAndWaitAsync(Uri target)
    {
        if (AccountBrowser.CoreWebView2 is null) return;
        var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        void Completed(object? sender, CoreWebView2NavigationCompletedEventArgs args)
        {
            AccountBrowser.NavigationCompleted -= Completed;
            completion.TrySetResult();
        }
        AccountBrowser.NavigationCompleted += Completed;
        LoadingPanel.Visibility = Visibility.Visible;
        AccountBrowser.CoreWebView2.Navigate(target.ToString());
        await completion.Task.WaitAsync(TimeSpan.FromSeconds(30));
    }

    private static bool IsOfficial(Uri uri) => uri.Scheme == Uri.UriSchemeHttps && (uri.Host.Equals("sologle.com", StringComparison.OrdinalIgnoreCase) || uri.Host.Equals("www.sologle.com", StringComparison.OrdinalIgnoreCase));

    private void PlaceOverOwner()
    {
        WindowStartupLocation = WindowStartupLocation.Manual;
        if (Owner is not null)
        {
            Left = Owner.Left + Math.Max(0, (Owner.ActualWidth - Width) / 2);
            Top = Owner.Top + Math.Max(0, (Owner.ActualHeight - Height) / 2);
            return;
        }
        Left = Math.Max(0, (SystemParameters.WorkArea.Width - Width) / 2);
        Top = Math.Max(0, (SystemParameters.WorkArea.Height - Height) / 2);
    }

    private void CloseButton_Click(object sender, RoutedEventArgs e)
    {
        _authFlow = false;
        Hide();
        ReturnedToWorkbench?.Invoke(this, EventArgs.Empty);
    }

    private void BackButton_Click(object sender, RoutedEventArgs e)
    {
        if (AccountBrowser.CoreWebView2?.CanGoBack == true) AccountBrowser.CoreWebView2.GoBack();
    }
}
