// Package kube resolves a pod's GhostKube identity via client-go.
package kube

import (
	"context"
	"fmt"
	"strings"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/cli-runtime/pkg/genericclioptions"
	"k8s.io/client-go/kubernetes"
)

// ServiceLabel is the label the mutating webhook watches (webhook/webhook.py).
const ServiceLabel = "ghostkube.io/service"

// GhostNoteIDEnvVar is the env var the webhook injects into app containers,
// value "svc:"+ServiceLabel (webhook/webhook.py make_patch_for_pod).
const GhostNoteIDEnvVar = "GHOST_NOTE_ID"

const svcPrefix = "svc:"

// Client wraps a client-go clientset plus the namespace resolved from the
// standard kubeconfig/--namespace overrides.
type Client struct {
	clientset *kubernetes.Clientset
	namespace string
}

// NewClient builds a Client from the standard client-go config flags
// (--kubeconfig, --namespace/-n, --context, ...). namespaceOverride, if
// non-empty, wins over whatever the flags/kubeconfig resolved.
func NewClient(flags *genericclioptions.ConfigFlags, namespaceOverride string) (*Client, error) {
	restConfig, err := flags.ToRESTConfig()
	if err != nil {
		return nil, fmt.Errorf("load kube config: %w", err)
	}

	clientset, err := kubernetes.NewForConfig(restConfig)
	if err != nil {
		return nil, fmt.Errorf("build kube client: %w", err)
	}

	namespace := namespaceOverride
	if namespace == "" {
		namespace, _, err = flags.ToRawKubeConfigLoader().Namespace()
		if err != nil {
			return nil, fmt.Errorf("resolve namespace: %w", err)
		}
	}

	return &Client{clientset: clientset, namespace: namespace}, nil
}

// GetPod fetches a pod by name in the resolved namespace.
func (c *Client) GetPod(ctx context.Context, name string) (*corev1.Pod, error) {
	pod, err := c.clientset.CoreV1().Pods(c.namespace).Get(ctx, name, metav1.GetOptions{})
	if err != nil {
		return nil, fmt.Errorf("get pod %s/%s: %w", c.namespace, name, err)
	}
	return pod, nil
}

// Namespace returns the resolved namespace.
func (c *Client) Namespace() string {
	return c.namespace
}

// Identity is a pod's resolved GhostKube identity.
type Identity struct {
	GhostNoteID string // e.g. "svc:auth-service" - always sent as ghost_note_id
	Query       string // service name with the "svc:" prefix stripped
}

// ResolveIdentity prefers the injected GHOST_NOTE_ID env var (Phase 8), and
// falls back to building "svc:"+label from ghostkube.io/service so the
// plugin still works before the webhook has run in a given cluster.
func ResolveIdentity(pod *corev1.Pod) (Identity, error) {
	for _, container := range pod.Spec.Containers {
		for _, env := range container.Env {
			if env.Name == GhostNoteIDEnvVar && env.Value != "" {
				return Identity{
					GhostNoteID: env.Value,
					Query:       strings.TrimPrefix(env.Value, svcPrefix),
				}, nil
			}
		}
	}

	if label := pod.Labels[ServiceLabel]; label != "" {
		return Identity{
			GhostNoteID: svcPrefix + label,
			Query:       label,
		}, nil
	}

	return Identity{}, fmt.Errorf(
		"pod %q has neither a %s env var nor a %s label - nothing to resolve",
		pod.Name, GhostNoteIDEnvVar, ServiceLabel,
	)
}
