// Command kubectl-ghost is the GhostKube "Voice": a kubectl plugin that
// surfaces Ghost Notes for a pod without leaving the terminal. Any
// executable named kubectl-ghost on $PATH becomes `kubectl ghost`.
package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"

	"github.com/spf13/cobra"
	"k8s.io/cli-runtime/pkg/genericclioptions"

	"ghostkube/internal/api"
	"ghostkube/internal/config"
	"ghostkube/internal/kube"
	"ghostkube/internal/render"
)

var (
	configFlags *genericclioptions.ConfigFlags
	topResults  int
	jsonOutput  bool
	timeout     time.Duration
)

func main() {
	if err := newRootCmd().Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func newRootCmd() *cobra.Command {
	configFlags = genericclioptions.NewConfigFlags(true)

	root := &cobra.Command{
		Use:          "ghost <pod-name>",
		Short:        "Show GhostKube notes for a pod",
		Args:         cobra.ExactArgs(1),
		SilenceUsage: true,
		RunE:         runShow,
	}
	// Without this, a persistent flag placed before "delete" (e.g.
	// `--top 1 delete pod X`) isn't stripped from the args handed to the
	// delete subcommand - Cobra's default Find() only removes the literal
	// "delete" token, not flags preceding it, so it would corrupt
	// delete's own (DisableFlagParsing) arg parsing. TraverseChildren
	// parses each level's flags as it descends instead.
	root.TraverseChildren = true

	root.PersistentFlags().IntVar(&topResults, "top", 5, "number of results to return")
	root.PersistentFlags().BoolVar(&jsonOutput, "json", false, "print the raw API response as JSON")
	root.PersistentFlags().DurationVar(&timeout, "timeout", 800*time.Millisecond, "Brain API request timeout")
	configFlags.AddFlags(root.PersistentFlags())

	root.AddCommand(newDeleteCmd())
	return root
}

func runShow(cmd *cobra.Command, args []string) error {
	podName := args[0]

	kubeClient, err := kube.NewClient(configFlags, "")
	if err != nil {
		return err
	}

	pod, err := kubeClient.GetPod(context.Background(), podName)
	if err != nil {
		return err
	}

	identity, err := kube.ResolveIdentity(pod)
	if err != nil {
		return err
	}

	resp, err := fetchNotes(identity)
	if err != nil {
		return err
	}

	if jsonOutput {
		return printJSON(resp)
	}

	display(os.Stdout, identity.GhostNoteID, resp.Results)
	collectFeedback(os.Stdin, os.Stdout, resp.Query, resp.Results)
	return nil
}

func newDeleteCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "delete pod NAME [kubectl-flags...]",
		Short: "Show the ghost note for a pod, confirm, then delete it via kubectl",
		Long: "The interception path (PRD Section 5): shows the pod's ghost note and\n" +
			"prompts for confirmation before delegating to the real `kubectl delete`.",
		// All args pass straight through to kubectl on confirmation, so cobra
		// must not try to interpret kubectl's own flags.
		DisableFlagParsing: true,
		SilenceUsage:       true,
		RunE:               runDelete,
	}
}

func runDelete(cmd *cobra.Command, args []string) error {
	if len(args) > 0 && (args[0] == "-h" || args[0] == "--help") {
		return cmd.Help()
	}

	podName, namespace, err := parsePodDeleteArgs(args)
	if err != nil {
		return err
	}

	kubeClient, err := kube.NewClient(configFlags, namespace)
	if err != nil {
		return err
	}

	pod, err := kubeClient.GetPod(context.Background(), podName)
	if err != nil {
		return err
	}

	identity, err := kube.ResolveIdentity(pod)
	if err != nil {
		return err
	}

	resp, err := fetchNotes(identity)
	if err != nil {
		return err
	}

	display(os.Stdout, identity.GhostNoteID, resp.Results)

	color := render.ColorEnabled(os.Stdout)
	render.DangerPrompt(os.Stdout, "\nProceed with caution? (y/n) ", color)

	reader := bufio.NewReader(os.Stdin)
	line, _ := reader.ReadString('\n')
	fmt.Println()
	if answer := strings.ToLower(strings.TrimSpace(line)); answer != "y" && answer != "yes" {
		fmt.Println("Aborted - nothing deleted.")
		os.Exit(1)
	}

	kubectlPath, err := exec.LookPath("kubectl")
	if err != nil {
		return fmt.Errorf("kubectl not found on PATH: %w", err)
	}

	fullArgs := append([]string{"delete"}, args...)
	delCmd := exec.Command(kubectlPath, fullArgs...)
	delCmd.Stdin, delCmd.Stdout, delCmd.Stderr = os.Stdin, os.Stdout, os.Stderr
	if err := delCmd.Run(); err != nil {
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) {
			os.Exit(exitErr.ExitCode())
		}
		return err
	}
	return nil
}

// parsePodDeleteArgs pulls the pod name and an optional -n/--namespace
// override out of raw `kubectl delete`-shaped args, e.g.
// ["pod", "auth-api-xyz"], ["pod/auth-api-xyz"], or
// ["pod", "auth-api-xyz", "-n", "ghostkube"]. Every other flag is left
// untouched for the real kubectl invocation.
func parsePodDeleteArgs(args []string) (podName, namespace string, err error) {
	var positional []string
	for i := 0; i < len(args); i++ {
		a := args[i]
		switch {
		case a == "-n" || a == "--namespace":
			if i+1 >= len(args) {
				return "", "", fmt.Errorf("missing value for %s", a)
			}
			namespace = args[i+1]
			i++
		case strings.HasPrefix(a, "--namespace="):
			namespace = strings.TrimPrefix(a, "--namespace=")
		case strings.HasPrefix(a, "-"):
			// Other kubectl flags aren't needed to resolve the pod. Only
			// `=`-joined values are recognized here (e.g. --grace-period=0);
			// a separate-token value would be misread as positional. Demo
			// scope is `ghost delete pod NAME`, not the full kubectl grammar.
		default:
			positional = append(positional, a)
		}
	}

	var resource string
	switch {
	case len(positional) == 1 && strings.Contains(positional[0], "/"):
		parts := strings.SplitN(positional[0], "/", 2)
		resource, podName = parts[0], parts[1]
	case len(positional) >= 2:
		resource, podName = positional[0], positional[1]
	default:
		return "", "", fmt.Errorf("usage: ghost delete pod NAME (or pod/NAME)")
	}

	if resource != "pod" && resource != "pods" {
		return "", "", fmt.Errorf("ghost delete only intercepts pod deletes, got resource %q", resource)
	}
	if podName == "" {
		return "", "", fmt.Errorf("no pod name given")
	}
	return podName, namespace, nil
}

func fetchNotes(identity kube.Identity) (*api.GhostNoteResponse, error) {
	client := api.New(config.APIURL(), timeout)
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	return client.GhostNote(ctx, api.GhostNoteRequest{
		Query:       identity.Query,
		TopResults:  topResults,
		GhostNoteID: identity.GhostNoteID,
	})
}

func printJSON(resp *api.GhostNoteResponse) error {
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	return enc.Encode(resp)
}

func display(w *os.File, ghostNoteID string, results []api.GhostNoteResult) {
	if len(results) == 0 {
		fmt.Fprintln(w, "No ghost notes found.")
		return
	}
	color := render.ColorEnabled(w)
	for i, r := range results {
		render.Note(w, ghostNoteID, r, color)
		if i < len(results)-1 {
			fmt.Fprintln(w)
		}
	}
}

// collectFeedback prompts up/down/skip per shown note. Interactive TTY only:
// skipped entirely for --json output or when stdin isn't a terminal (e.g.
// piped/scripted invocations), per Phase 11 item 5.
func collectFeedback(stdin, stdout *os.File, query string, results []api.GhostNoteResult) {
	if len(results) == 0 || !render.IsTerminal(stdin) {
		return
	}

	client := api.New(config.APIURL(), timeout)
	reader := bufio.NewReader(stdin)

	for _, r := range results {
		fmt.Fprint(stdout, "\nRate this note [u]p / [d]own / [s]kip: ")
		line, _ := reader.ReadString('\n')

		var rating string
		switch strings.ToLower(strings.TrimSpace(line)) {
		case "u", "up":
			rating = "up"
		case "d", "down":
			rating = "down"
		default:
			continue
		}

		ctx, cancel := context.WithTimeout(context.Background(), timeout)
		_, err := client.Feedback(ctx, api.FeedbackRequest{ChunkID: r.ChunkID, Query: query, Rating: rating})
		cancel()
		if err != nil {
			fmt.Fprintf(stdout, "  (feedback not recorded: %v)\n", err)
		}
	}
}
