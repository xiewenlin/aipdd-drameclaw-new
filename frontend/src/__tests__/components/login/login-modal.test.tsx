import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginModal } from "@/components/login/login-modal";

const requestGulongAuthMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/gulong-sso", () => ({
  requestGulongAuth: requestGulongAuthMock,
}));

describe("LoginModal", () => {
  beforeEach(() => {
    requestGulongAuthMock.mockReset();
  });

  it("delegates login to Gulong without rendering a short-drama dialog", () => {
    const view = render(
      <LoginModal open initialMode="login" onClose={() => undefined} />,
    );

    expect(requestGulongAuthMock).toHaveBeenCalledWith("login");
    expect(view.queryByRole("dialog")).toBeNull();
    expect(view.container).toBeEmptyDOMElement();
  });
});
