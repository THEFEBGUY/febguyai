import { Menu, Sparkles } from "lucide-react";

function MobileTopBar({ isCodeWorkspace, onOpenMenu }) {
  return (
    <header className="fg-mobile-topbar" aria-label="Mobile header">
      <button
        type="button"
        className="fg-mobile-icon-button"
        aria-label="Open navigation"
        onClick={onOpenMenu}
      >
        <Menu />
      </button>

      <div className="fg-mobile-brand">
        <img src="/sidebar-logo.png" alt="" />
        <div>
          <strong>FebGuyAI</strong>
          <span>By Pranav Amble</span>
        </div>
      </div>

      <span className="fg-mobile-mode-pill">
        <Sparkles />
        {isCodeWorkspace ? "Code" : "Chat"}
      </span>
    </header>
  );
}

export default MobileTopBar;
