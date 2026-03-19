import { create } from "zustand";

type BookmarkStore = {
  bookmarkedTurns: Set<number>;
  sessionId: string | null;
  isLoading: boolean;
  setSessionId: (sessionId: string | null) => void;
  loadBookmarks: (sessionId: string) => Promise<void>;
  toggleBookmark: (turnIndex: number) => Promise<void>;
  isBookmarked: (turnIndex: number) => boolean;
};

export const useBookmarkStore = create<BookmarkStore>((set, get) => ({
  bookmarkedTurns: new Set<number>(),
  sessionId: null,
  isLoading: false,

  setSessionId: (sessionId) => {
    set({ sessionId });
    if (sessionId) {
      get().loadBookmarks(sessionId);
    } else {
      set({ bookmarkedTurns: new Set() });
    }
  },

  loadBookmarks: async (sessionId: string) => {
    set({ isLoading: true });
    try {
      const response = await fetch(`/api/sessions/${sessionId}/bookmarks`);
      if (response.ok) {
        const data = await response.json();
        set({ bookmarkedTurns: new Set(data.bookmarked_turns) });
      }
    } catch (error) {
      console.error("Failed to load bookmarks:", error);
    } finally {
      set({ isLoading: false });
    }
  },

  toggleBookmark: async (turnIndex: number) => {
    const { sessionId, bookmarkedTurns } = get();
    if (!sessionId) return;

    const isCurrentlyBookmarked = bookmarkedTurns.has(turnIndex);
    const newBookmarks = new Set(bookmarkedTurns);

    // Optimistic update
    if (isCurrentlyBookmarked) {
      newBookmarks.delete(turnIndex);
    } else {
      newBookmarks.add(turnIndex);
    }
    set({ bookmarkedTurns: newBookmarks });

    try {
      if (isCurrentlyBookmarked) {
        // Remove bookmark
        await fetch(`/api/sessions/${sessionId}/bookmark/${turnIndex}`, {
          method: "DELETE",
        });
      } else {
        // Add bookmark
        await fetch(`/api/sessions/${sessionId}/bookmark`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ turn_index: turnIndex }),
        });
      }
    } catch (error) {
      console.error("Failed to toggle bookmark:", error);
      // Revert on error
      set({ bookmarkedTurns: bookmarkedTurns });
    }
  },

  isBookmarked: (turnIndex: number) => {
    return get().bookmarkedTurns.has(turnIndex);
  },
}));
