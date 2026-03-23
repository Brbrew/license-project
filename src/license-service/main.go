package main

import (
	"database/sql"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strings"

	"github.com/MicahParks/keyfunc/v2"
	"github.com/golang-jwt/jwt/v5"
	"github.com/golang-jwt/jwt/v5/request"
	_ "github.com/lib/pq"
)

var db *sql.DB
var jwks *keyfunc.JWKS

type LicenseResponse struct {
	UserID   string   `json:"user_id"`
	Features []string `json:"features"`
}

type Feature struct {
	Name        string `json:"name"`
	Description string `json:"description"`
}

type FeaturesResponse struct {
	Features []Feature `json:"features"`
}

func main() {
	var err error

	// Connect to Postgres
	db, err = sql.Open("postgres", os.Getenv("DB_URL"))
	if err != nil {
		log.Fatal(err)
	}

	// Fetch Keycloak's public keys so we can validate JWTs locally
	// This is the key OAuth2 pattern: the resource server never calls back
	// to the IdP on every request — it validates the token signature offline.
	jwks, err = keyfunc.Get(os.Getenv("KEYCLOAK_JWKS_URL"), keyfunc.Options{
		RefreshErrorHandler: func(err error) {
			log.Printf("JWKS refresh error: %v", err)
		},
	})

	if err != nil {
		log.Fatal("Failed to fetch JWKS:", err)
	}

	http.HandleFunc("/features", requireToken(handleFeatures))
	http.HandleFunc("/admin/features", requireToken(handleAllFeatures))
	http.HandleFunc("/admin/assign", requireToken(handleAssign))
	http.HandleFunc("/admin/revoke", requireToken(handleRevoke))
	http.HandleFunc("/admin/users/{user_id}/features", requireToken(handleUserFeatures))

	log.Println("License service listening on :9000")
	log.Fatal(http.ListenAndServe(":9000", nil))
}

// requireToken is middleware that validates the Bearer JWT on every request.
// This is the core OAuth2 resource server pattern.
func requireToken(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		tokenStr, err := request.HeaderExtractor{"Authorization"}.ExtractToken(r)
		if err != nil || !strings.HasPrefix(tokenStr, "Bearer ") {
			http.Error(w, "missing token", http.StatusUnauthorized)
			return
		}
		tokenStr = strings.TrimPrefix(tokenStr, "Bearer ")

		token, err := jwt.Parse(tokenStr, jwks.Keyfunc,
			jwt.WithoutClaimsValidation(),
		)

		if err != nil || !token.Valid {
			http.Error(w, "invalid token", http.StatusUnauthorized)
			return
		}

		// Pass the parsed claims to the handler via context in a real app.
		// Keeping it simple here — just call the handler.
		r.Header.Set("X-User-ID", token.Claims.(jwt.MapClaims)["sub"].(string))
		next(w, r)
	}
}

// handleFeatures returns the list of enabled features for the calling user.
func handleFeatures(w http.ResponseWriter, r *http.Request) {
	userID := r.Header.Get("X-User-ID")
	rows, err := db.Query("SELECT feature FROM licenses WHERE user_id = $1", userID)
	if err != nil {
		http.Error(w, "db error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	features := []string{}
	for rows.Next() {
		var f string
		rows.Scan(&f)
		features = append(features, f)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(LicenseResponse{UserID: userID, Features: features})
}

// handleAllFeatures returns all available features in the system.
func handleAllFeatures(w http.ResponseWriter, r *http.Request) {
	rows, err := db.Query("SELECT name, description FROM features")
	if err != nil {
		http.Error(w, "db error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	features := []Feature{}

	for rows.Next() {
		var name, description string
		rows.Scan(&name, &description)
		features = append(features, Feature{Name: name, Description: description})
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(FeaturesResponse{Features: features})
}

// handleUserFeatures returns the list of assigned features for a specific user.
func handleUserFeatures(w http.ResponseWriter, r *http.Request) {
	userID := r.PathValue("user_id")
	rows, err := db.Query("SELECT feature FROM licenses WHERE user_id = $1", userID)
	if err != nil {
		http.Error(w, "db error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	features := []string{}
	for rows.Next() {
		var f string
		rows.Scan(&f)
		features = append(features, f)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(LicenseResponse{UserID: userID, Features: features})
}

func handleAssign(w http.ResponseWriter, r *http.Request) {
	// TODO: add an "admin" role check on the token claims
	var body struct {
		UserID  string `json:"user_id"`
		Feature string `json:"feature"`
	}
	json.NewDecoder(r.Body).Decode(&body)
	db.Exec("INSERT INTO licenses (user_id, feature) VALUES ($1, $2) ON CONFLICT DO NOTHING",
		body.UserID, body.Feature)
	w.WriteHeader(http.StatusNoContent)
}

func handleRevoke(w http.ResponseWriter, r *http.Request) {
	var body struct {
		UserID  string `json:"user_id"`
		Feature string `json:"feature"`
	}
	json.NewDecoder(r.Body).Decode(&body)
	db.Exec("DELETE FROM licenses WHERE user_id = $1 AND feature = $2", body.UserID, body.Feature)
	w.WriteHeader(http.StatusNoContent)
}
