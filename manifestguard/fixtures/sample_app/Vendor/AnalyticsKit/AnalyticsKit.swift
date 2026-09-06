import Foundation

final class AnalyticsKit {

    // Required-reason API: Disk space, used to decide whether to buffer
    // events on disk before uploading a batch.
    func hasRoomToBuffer() -> Bool {
        let values = try? URL(fileURLWithPath: NSTemporaryDirectory())
            .resourceValues(forKeys: [.volumeAvailableCapacityKey])
        let free = values?.volumeAvailableCapacity ?? 0
        return free > 10_000_000
    }
}
