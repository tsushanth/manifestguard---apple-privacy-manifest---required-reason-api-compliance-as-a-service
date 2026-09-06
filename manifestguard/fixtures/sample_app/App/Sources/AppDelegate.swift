import UIKit

@main
class AppDelegate: UIResponder, UIApplicationDelegate {

    func application(_ application: UIApplication,
                      didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        // Required-reason API: UserDefaults, used to remember onboarding state.
        let defaults = UserDefaults.standard
        defaults.set(true, forKey: "didShowOnboarding")
        return true
    }
}
