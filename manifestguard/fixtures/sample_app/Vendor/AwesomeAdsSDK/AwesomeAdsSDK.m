#import "AwesomeAdsSDK.h"

@implementation AwesomeAdsSDK

- (void)trackSession {
    // Required-reason API: UserDefaults, used to cache the ad session id.
    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    [defaults setObject:@"session-123" forKey:@"ads_session_id"];

    // Required-reason API: File timestamp, used to age out cached creatives.
    NSDictionary *attrs = [[NSFileManager defaultManager] attributesOfItemAtPath:@"/tmp/creative.png" error:nil];
    NSDate *modified = [attrs fileModificationDate];
    (void)modified;
}

@end
