// Package render prints Ghost Notes to a terminal per the Phase 10 style
// sheet (design/terminal.png): muted id line, accent note body, muted
// source/relevance, danger prompts.
package render

import (
	"fmt"
	"io"
	"os"

	"golang.org/x/term"

	"ghostkube/internal/api"
)

const (
	colorMuted  = "#8B97A8"
	colorAccent = "#A78BFA"
	colorDanger = "#F85149"
	reset       = "\x1b[0m"
)

// IsTerminal reports whether f is an interactive terminal.
func IsTerminal(f *os.File) bool {
	return term.IsTerminal(int(f.Fd()))
}

// ColorEnabled reports whether w should receive ANSI color: a real terminal,
// and NO_COLOR (https://no-color.org) unset.
func ColorEnabled(w *os.File) bool {
	if os.Getenv("NO_COLOR") != "" {
		return false
	}
	return IsTerminal(w)
}

func ansi(hex string) (int, int, int) {
	var r, g, b int
	fmt.Sscanf(hex, "#%02x%02x%02x", &r, &g, &b)
	return r, g, b
}

func colorize(text, hex string, enabled bool) string {
	if !enabled {
		return text
	}
	r, g, b := ansi(hex)
	return fmt.Sprintf("\x1b[38;2;%d;%d;%dm%s%s", r, g, b, text, reset)
}

// Note writes one Ghost Note result: 👻 id (muted), note text (accent),
// source path (muted), relevance score (muted).
func Note(w io.Writer, ghostNoteID string, result api.GhostNoteResult, color bool) {
	fmt.Fprintln(w, colorize(fmt.Sprintf("👻 %s", ghostNoteID), colorMuted, color))
	fmt.Fprintln(w, colorize(result.Text, colorAccent, color))

	path, _ := result.Metadata["path"].(string)
	if path == "" {
		path = "unknown"
	}
	fmt.Fprintln(w, colorize(fmt.Sprintf("source: %s", path), colorMuted, color))
	fmt.Fprintln(w, colorize(fmt.Sprintf("relevance: %.2f", result.RelevanceScore), colorMuted, color))
}

// DangerPrompt renders the "Proceed with caution? (y/n)" prompt in the
// danger color, matching design/terminal.png.
func DangerPrompt(w io.Writer, text string, color bool) {
	fmt.Fprint(w, colorize(text, colorDanger, color))
}
