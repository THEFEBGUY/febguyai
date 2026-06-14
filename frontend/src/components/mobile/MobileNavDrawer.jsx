import { useEffect, useState } from "react";
import {
  Code2,
  Download,
  Lock,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Pin,
  Plus,
  Settings2,
  Trash2,
  UserRound,
  X
} from "lucide-react";

function MobileNavDrawer({
  activeChatId,
  chats,
  getChatSubtitle,
  isAccountProfile,
  isCodeWorkspace,
  onClose,
  onDeleteChat,
  onExportChat,
  onNewChat,
  onOpenChat,
  onRenameChat,
  onSettings,
  onSignIn,
  onSwitchProfile,
  onSwitchWorkspace,
  onTogglePinChat,
  open,
  profileName,
  sessionMode
}) {
  const [openActionChatId, setOpenActionChatId] = useState("");

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose, open]);

  useEffect(() => {
    if (!open) {
      setOpenActionChatId("");
    }
  }, [open]);

  return (
    <div className={`fg-mobile-drawer-root ${open ? "open" : ""}`} aria-hidden={!open} inert={!open ? "" : undefined}>
      <button
        type="button"
        className="fg-mobile-drawer-backdrop"
        aria-label="Close navigation"
        onClick={onClose}
      />

      <aside
        className="fg-mobile-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="FebGuyAI navigation"
      >
        <div className="fg-mobile-drawer-header">
          <div className="fg-mobile-drawer-brand">
            <img src="/sidebar-logo.png" alt="" />
            <div>
              <strong>FebGuyAI</strong>
              <span>By Pranav Amble</span>
            </div>
          </div>
          <button
            type="button"
            className="fg-mobile-close-button"
            aria-label="Close navigation"
            onClick={onClose}
          >
            <X />
          </button>
        </div>

        <div className="fg-mobile-profile-strip">
          <span>{sessionMode === "guest" ? "Guest" : "Profile"}</span>
          <strong>{profileName || "FebGuyAI"}</strong>
        </div>

        <button type="button" className="fg-mobile-primary-action" onClick={onNewChat}>
          <Plus />
          {isCodeWorkspace ? "New Code Chat" : "New Chat"}
        </button>

        <nav className="fg-mobile-nav-actions" aria-label="Workspace navigation">
          <button
            type="button"
            className={!isCodeWorkspace ? "active" : ""}
            onClick={() => onSwitchWorkspace("chat")}
          >
            <MessageSquare />
            Chat
          </button>
          <button
            type="button"
            className={isCodeWorkspace ? "active" : ""}
            onClick={() => onSwitchWorkspace("code")}
          >
            <Code2 />
            Code Studio
          </button>
          <button type="button" onClick={onSettings}>
            <Settings2 />
            Settings
          </button>
          {sessionMode === "guest" ? (
            <button type="button" onClick={onSignIn}>
              <Lock />
              Sign In
            </button>
          ) : isAccountProfile ? (
            <button type="button" onClick={onSwitchProfile}>
              <UserRound />
              Profile
            </button>
          ) : null}
        </nav>

        <div className="fg-mobile-history">
          <div className="fg-mobile-history-title">
            <span>{isCodeWorkspace ? "Code Studio Chats" : "Previous Chats"}</span>
          </div>

          <div className="fg-mobile-history-list">
            {!chats.length && (
              <div className="fg-mobile-history-empty">
                {isCodeWorkspace ? "No code chats yet." : "No chats yet."}
              </div>
            )}
            {chats.map((chatItem, index) => (
              <div
                key={chatItem.id}
                className={activeChatId === chatItem.id ? "fg-mobile-history-item active" : "fg-mobile-history-item"}
              >
                <button
                  type="button"
                  className="fg-mobile-history-open"
                  onClick={() => onOpenChat(chatItem)}
                >
                  <span className="fg-mobile-chat-index">{chatItem.pinned ? <Pin /> : index + 1}</span>
                  <span>
                    <strong>{chatItem.title || "New Chat"}</strong>
                    <small>{getChatSubtitle(chatItem)}</small>
                  </span>
                </button>

                <button
                  type="button"
                  className="fg-mobile-history-more"
                  aria-label={`Chat actions for ${chatItem.title || "New Chat"}`}
                  aria-expanded={openActionChatId === chatItem.id}
                  onClick={(event) => {
                    event.stopPropagation();
                    setOpenActionChatId(current => current === chatItem.id ? "" : chatItem.id);
                  }}
                >
                  <MoreHorizontal />
                </button>

                {openActionChatId === chatItem.id && (
                  <div className="fg-mobile-chat-actions-menu" role="menu">
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setOpenActionChatId("");
                        onTogglePinChat?.(chatItem);
                      }}
                    >
                      <Pin />
                      {chatItem.pinned ? "Unpin" : "Pin"}
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setOpenActionChatId("");
                        onRenameChat?.(chatItem);
                      }}
                    >
                      <Pencil />
                      Rename
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setOpenActionChatId("");
                        onExportChat?.(chatItem);
                      }}
                    >
                      <Download />
                      Download
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      className="danger"
                      onClick={() => {
                        setOpenActionChatId("");
                        onDeleteChat?.(chatItem);
                      }}
                    >
                      <Trash2 />
                      Delete
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}

export default MobileNavDrawer;
