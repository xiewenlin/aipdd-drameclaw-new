using Gulong.ShortDrama.Models;

namespace Gulong.ShortDrama.Services;

public sealed class AccountSessionService : IDisposable
{
    private readonly OfficialApiClient _api;
    private readonly AccountWebWindow _window;

    public AccountSessionService(OfficialApiClient api, MainWindow owner)
    {
        _api = api;
        _window = new AccountWebWindow { Owner = owner };
    }

    public event EventHandler? ReturnedToWorkbench
    {
        add => _window.ReturnedToWorkbench += value;
        remove => _window.ReturnedToWorkbench -= value;
    }

    public async Task<ApiResult<UserAccount>> TryRestoreAsync()
    {
        try
        {
            await _window.InitializeBrowserAsync();
            await _api.ImportBrowserCookiesAsync(_window.Browser);
            return await _api.ReadAccountAsync();
        }
        catch (Exception error)
        {
            return ApiResult<UserAccount>.Failure("BROWSER_ERROR", $"古龙账号组件初始化失败：{error.Message}");
        }
    }

    public async Task<ApiResult<UserAccount>> EnsureAuthenticatedAsync(AuthMode mode)
    {
        var current = await TryRestoreAsync();
        if (current.IsSuccess) return current;

        var completed = await _window.ShowAuthAsync(mode);
        if (!completed) return ApiResult<UserAccount>.Failure("AUTH_CANCELLED", mode == AuthMode.Register ? "注册已取消" : "登录已取消");
        await _api.ImportBrowserCookiesAsync(_window.Browser);
        return await _api.ReadAccountAsync();
    }

    public async Task OpenAccountPageAsync()
    {
        await _window.ShowOfficialPageAsync("/account", "古龙用户中心");
    }

    public async Task OpenSubscriptionPageAsync()
    {
        await _window.ShowOfficialPageAsync("/pricing", "古龙会员订阅");
    }

    public async Task OpenRechargePageAsync()
    {
        await _window.ShowOfficialPageAsync("/pricing#recharge", "古龙账户充值");
    }

    public void Dispose() => _window.ForceClose();
}
