# Privacy Policy

LaTeX Editor is a desktop application that runs on your computer. It has no user accounts, advertising, analytics or telemetry, and the developer does not receive any data from it.

This policy describes what the application stores on your computer and the only two kinds of network requests it makes.

*Last updated: 2026-09-28. Applies to LaTeX Editor 1.0.19 and later.*

## Data stored on your computer

Everything in this section stays on your computer. Nothing is uploaded.

- **Your documents.** The application reads and writes only the files and folders you open. Compiling runs the TeX installation on your computer (on Windows through WSL); the output files (PDF, log, auxiliary and SyncTeX files) are written next to your document. Images you paste are saved into your project folder; the clipboard is read only when you paste.
- **Settings.** Preferences such as language, theme and editor options, the window layout, the open tabs, the last opened folder, recent files and the time of the last update check. They are kept in your operating system's standard settings store for your user account: the registry under `HKEY_CURRENT_USER\Software\LatexEditor` on Windows, `~/.config/LatexEditor` on Linux and `~/Library/Preferences` on macOS.
- **Crash recovery.** While a tab has unsaved changes, a copy of its text is saved every 30 seconds to a `recovery` folder inside the application data folder (`%LOCALAPPDATA%\LatexEditor` on Windows, `~/.local/share/LatexEditor` on Linux, `~/Library/Application Support/LatexEditor` on macOS), so that it can be restored after a crash. A copy is deleted when you save or close its document, when you choose Discard at startup, and when you close the application normally. After you restore a copy, it is kept until you save the document, as protection against another crash.
- **Log file.** `latex-editor.log` in the same application data folder records technical events, such as the paths of the files you open and the results of compiling, to help diagnose problems. It is limited to 1 MB with five older copies, and it is never sent anywhere.
- **Personal dictionary.** Words you add to the spell checker are saved in a text file in your local application data folder.
- **Autosave (on by default).** Every 3 minutes, open documents that already have a file are saved to that file. You can turn it off or change the interval in View → Editor Settings.
- **Snapshots (only when you use them).** The Snapshot command (Ctrl+K) creates a standard Git repository (`.git`) inside your project folder.
- **File association (installed builds).** On Windows the application adds itself to the "Open with" list for `.tex` files for your user account (under `HKEY_CURRENT_USER\Software\Classes`); on Linux it adds a desktop entry under `~/.local/share/applications`.

To remove all of this data, uninstall the application and delete the application data folder and the settings listed above.

## Network requests

The application connects to the internet only in these two cases, always over HTTPS.

1. **Update check.** At startup (at most once every 24 hours) and when you choose Help → Check for Updates, the application asks the GitHub Releases API (`api.github.com`) for the latest release of LaTeX Editor. The request contains only the application's name and version in its User-Agent header (`LaTeX-Editor/<version>`); no document content or personal data is sent. If a newer version exists, the application tells you and links to the release page; it never downloads or installs anything by itself. The automatic check cannot currently be turned off in the settings.
2. **DOI lookup.** Only when you use Add Source by DOI, the DOI you type is sent to Crossref (`api.crossref.org`) and, if Crossref has no record of it, to `doi.org`, to download its bibliography entry. The User-Agent header contains only the application's name and project address. The entry is added to your `.bib` file only after you confirm it.

Like any internet request, these reveal your IP address to the server you connect to. The privacy policies of GitHub, Crossref and the DOI Foundation apply to these requests.

Links you click (for example in a PDF or in the About window) open in your web browser. Programs you use through the application, such as your TeX distribution, WSL or pandoc, may access the network on their own (for example, MiKTeX installing a missing package); their own privacy policies apply.

## Contact

Questions about this policy: open an issue at https://github.com/s-balli/latex-editor/issues. Security issues: use the private "Report a vulnerability" button on the repository's Security tab.

Changes to this policy are published in this file, and its history is kept in the repository.
