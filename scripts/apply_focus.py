#!/usr/bin/env python3
"""Adds Focus Mode (hide video thumbnails) to Opaline.

Run from the repository root: python3 scripts/apply_focus.py
Every edit is an exact-text replacement and asserts that it matched exactly
once, so it fails loudly instead of half-applying. Safe to run only once.
"""
import pathlib
import sys

ROOT = pathlib.Path("Opaline")


def edit(path, old, new):
    p = ROOT / path
    s = p.read_text(encoding="utf-8")
    n = s.count(old)
    if n != 1:
        sys.exit(f"FAILED: {path}: expected 1 match, found {n} for: {old[:70]!r}")
    p.write_text(s.replace(old, new), encoding="utf-8")


if (ROOT / "Core/Common/FocusMode.swift").exists():
    sys.exit("Focus Mode is already applied; nothing to do.")

# 1. UserDefaults key
edit("Core/Config/UserDefaultsKeys.swift",
"""    enum Search {
        static let history = "search_history"
    }
""",
"""    enum Focus {
        /// Video preview images are withheld; absent = hidden.
        static let hideThumbnails = "focus_hideThumbnails"
    }

    enum Search {
        static let history = "search_history"
    }
""")

# 2. New FocusMode type
(ROOT / "Core/Common/FocusMode.swift").write_text('''import Foundation

/// Focus Mode: withholds the pieces of the feed designed to pull the eye,
/// so a video is chosen by its title and channel instead of by a
/// thumbnail. Everything stays usable; only the pictures go.
enum FocusMode {
    /// On unless the user turned it off. Setting it tells every live
    /// thumbnail view to re-apply, so the change shows immediately.
    static var hidesThumbnails: Bool {
        get {
            UserDefaults.standard.object(
                forKey: UserDefaultsKeys.Focus.hideThumbnails
            ) as? Bool ?? true
        }
        set {
            UserDefaults.standard.set(
                newValue, forKey: UserDefaultsKeys.Focus.hideThumbnails
            )
            NotificationCenter.default.post(
                name: .focusModeDidChange,
                object: nil
            )
        }
    }
}

extension Notification.Name {
    static let focusModeDidChange = Notification.Name(
        "focusModeDidChange"
    )
}
''', encoding="utf-8")

# 3. ThumbnailImageView: withhold video previews
f = "Core/Common/ThumbnailImageView.swift"
edit(f, """    private var hasFailed = false

    /// Zero derives""", """    private var hasFailed = false
    /// The video preview this view was last asked to show, kept even while
    /// Focus Mode withholds it so a settings change can restore or hide it
    /// without the owning cell being reconfigured.
    private var videoThumbnailRequest: (url: URL, videoId: String?)?

    /// Zero derives""")
edit(f, """            name: .thumbnailQualityDidChange,
            object: nil
        )
    }
""", """            name: .thumbnailQualityDidChange,
            object: nil
        )
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(focusModeDidChange),
            name: .focusModeDidChange,
            object: nil
        )
    }
""")
edit(f, """    override func layoutSubviews() {
        super.layoutSubviews()
        startLoadingIfNeeded()
    }
""", """    /// Focus Mode was switched, so show or withhold the current preview.
    @objc
    private func focusModeDidChange() {
        guard let request = videoThumbnailRequest else {
            return
        }
        setVideoThumbnail(url: request.url, videoId: request.videoId)
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        startLoadingIfNeeded()
    }

    /// Entry point for video preview images (feed cards, shelves, up next).
    /// Avatars and banners keep using `setImage`: Focus Mode is about the
    /// pictures that sell a video, not the ones that identify a channel.
    /// While it is on the view stays a flat placeholder and nothing is
    /// downloaded.
    func setVideoThumbnail(url: URL, videoId: String? = nil) {
        guard FocusMode.hidesThumbnails else {
            videoThumbnailRequest = (url, videoId)
            setImage(url: url, videoId: videoId)
            return
        }
        cancel()
        videoThumbnailRequest = (url, videoId)
    }
""")
edit(f, """    func cancel() {
        loadToken?.cancel()
        loadToken = nil
        currentURL = nil
""", """    func cancel() {
        loadToken?.cancel()
        loadToken = nil
        videoThumbnailRequest = nil
        currentURL = nil
""")

# 4. No prefetch while thumbnails are hidden
edit("Core/Common/ThumbnailImageView+Cache.swift", """        maxPixelSize: Int = ThumbnailSizing.defaultPixelSize
    ) {
        ThumbnailLoader.shared.prefetch(""", """        maxPixelSize: Int = ThumbnailSizing.defaultPixelSize
    ) {
        // Only video previews are prefetched; with Focus Mode on they are
        // never shown, so fetching them would just spend data.
        guard !FocusMode.hidesThumbnails else {
            return
        }
        ThumbnailLoader.shared.prefetch(""")

# 5. Call sites that show video previews
edit("Core/Common/VideoCell.swift", """        thumbnail.setImage(
            url: url,
            videoId: video.isShort ? nil : video.id
        )""", """        thumbnail.setVideoThumbnail(
            url: url,
            videoId: video.isShort ? nil : video.id
        )""")
edit("Core/Common/SubscriptionVideoCell.swift", """            thumbnail.setImage(
                url: url,
                videoId: video.isShort ? nil : video.id
            )""", """            thumbnail.setVideoThumbnail(
                url: url,
                videoId: video.isShort ? nil : video.id
            )""")
edit("Core/Common/ShortThumbnailCell.swift",
     "            poster.setImage(url: url)",
     "            poster.setVideoThumbnail(url: url)")
edit("Features/Player/AutoplayOverlayView.swift",
     "            thumbnailView.setImage(url: url)",
     "            thumbnailView.setVideoThumbnail(url: url)")
edit("Features/Library/PlaylistCell.swift",
     "            thumb.setImage(url: url)",
     "            thumb.setVideoThumbnail(url: url)")

# 6. Settings -> Focus Mode page
f = "Core/Common/SettingsViewController.swift"
edit(f, "        case pageSponsorBlock, pageCache, pageDebug, pageDownloads\n",
        "        case pageSponsorBlock, pageCache, pageDebug, pageDownloads\n"
        "        case pageFocus, hideThumbnails\n")
edit(f, "        case sponsorBlock, cache, debug, downloads\n    }",
        "        case sponsorBlock, cache, debug, downloads, focus\n    }")
edit(f, """        case .pageAppearance, .pageLanguage, .pagePlayback, .pageShorts,
             .pageSponsorBlock, .pageCache, .pageDebug, .pageDownloads:""",
        """        case .pageAppearance, .pageLanguage, .pagePlayback, .pageShorts,
             .pageSponsorBlock, .pageCache, .pageDebug, .pageDownloads,
             .pageFocus:""")
edit(f, """        case .showShorts:
            return makeShowShortsCell()
""", """        case .hideThumbnails:
            return makeToggleCell(
                "settings.row.hideThumbnails".localized,
                isOn: FocusMode.hidesThumbnails
            ) {
                FocusMode.hidesThumbnails = $0
            }
        case .showShorts:
            return makeShowShortsCell()
""")

f = "Core/Common/SettingsViewController+Pages.swift"
edit(f, """        .downloads: "settings.section.downloads"
    ]""", """        .downloads: "settings.section.downloads",
        .focus: "settings.section.focus"
    ]""")
edit(f, """        .pageDebug: .debug
    ]""", """        .pageDebug: .debug,
        .pageFocus: .focus
    ]""")
edit(f, """        case .downloads:
            return downloadsSections
        }""", """        case .downloads:
            return downloadsSections
        case .focus:
            return focusSections
        }""")
edit(f, """                    .pageAppearance, .pageLanguage,
                    .pagePlayback, .pageShorts, .pageDownloads,""",
        """                    .pageFocus, .pageAppearance, .pageLanguage,
                    .pagePlayback, .pageShorts, .pageDownloads,""")
edit(f, """    private var downloadsSections: [Section] {""", """    private var focusSections: [Section] {
        [
            Section(
                header: nil,
                footer: "settings.footer.focus".localized,
                rows: [.hideThumbnails]
            )
        ]
    }

    private var downloadsSections: [Section] {""")

# 7. English strings (other languages fall back to English)
p = ROOT / "en.lproj/Localizable.strings"
s = p.read_text(encoding="utf-8")
if not s.endswith("\n"):
    s += "\n"
s += '''"settings.section.focus" = "Focus Mode";
"settings.row.hideThumbnails" = "Hide thumbnails";
"settings.footer.focus" = "Video thumbnails are replaced by a plain box, so you pick what to watch from the title and channel instead of the picture. Nothing is downloaded for them. Channel avatars stay.";
'''
p.write_text(s, encoding="utf-8")

print("Focus Mode applied: 11 files edited, 1 added.")
