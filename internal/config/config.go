// Package config resolves the Brain API base URL.
package config

import (
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

const DefaultAPIURL = "http://localhost:8000"

type fileConfig struct {
	APIURL string `yaml:"api_url"`
}

// APIURL resolves the Brain API base URL: GHOSTKUBE_API env var, then
// api_url in ~/.ghostkube.yaml, then DefaultAPIURL.
func APIURL() string {
	if v := os.Getenv("GHOSTKUBE_API"); v != "" {
		return v
	}

	home, err := os.UserHomeDir()
	if err != nil {
		return DefaultAPIURL
	}

	data, err := os.ReadFile(filepath.Join(home, ".ghostkube.yaml"))
	if err != nil {
		return DefaultAPIURL
	}

	var cfg fileConfig
	if err := yaml.Unmarshal(data, &cfg); err != nil || cfg.APIURL == "" {
		return DefaultAPIURL
	}

	return cfg.APIURL
}
