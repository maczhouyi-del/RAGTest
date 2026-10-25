fn main() {
    println!(
        "cargo:rustc-env=RAGSYSTEM_HOST={}",
        std::env::var("TARGET").expect("TARGET")
    );
    tauri_build::build();
}
