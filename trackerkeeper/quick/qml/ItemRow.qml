// One tracked thing, two lines tall:
//   ● Name                          2h
//     1.2.9 → 1.3.0 · Android
// Colour is reserved for NEWS: the dot and the version go green only for an
// update you haven't seen yet. One you've seen but not installed keeps a grey
// dot and plain text; an item that's current has no dot and reads quieter.
// Tap → the detail sheet. Swipe right → mark updated (when there's an update).
import QtQuick
import QtQuick.Controls

SwipeDelegate {
    id: row
    // model roles, set by the ListView
    required property string name
    required property string platform
    required property string versionLine
    required property string age
    required property string error
    required property bool hasUpdate
    required property bool isNew

    signal opened()
    signal markUpdated()

    objectName: "row_" + name
    width: ListView.view ? ListView.view.width : 360
    height: 72
    padding: 0
    focusPolicy: Qt.NoFocus
    hoverEnabled: false
    swipe.enabled: hasUpdate
    onClicked: if (swipe.position === 0) row.opened()
    swipe.onCompleted: row.markUpdated()

    background: Rectangle {
        color: row.pressed && row.swipe.position === 0 ? theme.surface : theme.background
    }

    // revealed under the row as it slides right
    swipe.left: Rectangle {
        width: row.width
        height: row.height
        color: theme.surface
        Row {
            anchors.verticalCenter: parent.verticalCenter
            x: 20
            spacing: 10
            Icon { anchors.verticalCenter: parent.verticalCenter; name: "check"; tint: theme.text; size: 22 }
            Label {
                anchors.verticalCenter: parent.verticalCenter
                text: qsTr("Mark updated")
                color: theme.text
                font.pixelSize: 15
                font.weight: Font.Medium
            }
        }
    }

    contentItem: Item {
        Rectangle {  // the status dot — its column is kept so names line up
            x: 16
            y: 21
            width: 8
            height: 8
            radius: 4
            visible: row.hasUpdate
            color: row.isNew ? theme.accent : theme.textFaint
        }
        Label {
            id: nameLabel
            x: 36
            y: 14
            width: parent.width - x - ageLabel.implicitWidth - 28
            text: row.name
            color: row.hasUpdate ? theme.text : theme.textDim
            font.pixelSize: 16
            font.weight: row.hasUpdate ? Font.Medium : Font.Normal
            elide: Text.ElideRight
        }
        Label {
            id: ageLabel
            anchors.right: parent.right
            anchors.rightMargin: 16
            anchors.baseline: nameLabel.baseline
            text: row.age
            color: theme.textFaint
            font.pixelSize: 13
        }
        Label {  // version line — the platform rides at the end, quieter
            x: 36
            y: 40
            width: parent.width - x - 16
            elide: Text.ElideRight
            textFormat: Text.StyledText
            font.pixelSize: 14
            function esc(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;") }
            // news green · pending (seen) mid-grey · current faint — the name
            // line carries the weight, this line only says where it's going.
            readonly property color versionColour: row.isNew ? theme.accent
                                                 : row.hasUpdate ? theme.textDim : theme.textFaint
            text: "<font color='" + versionColour + "'>" + esc(row.versionLine) + "</font>"
                  + (row.error !== "" ? "<font color='" + theme.warning + "'>  ·  "
                                        + esc(row.error) + "</font>"
                     : row.platform ? "<font color='" + theme.textFaint + "'>  ·  "
                                      + esc(row.platform) + "</font>" : "")
        }
        Rectangle {  // hairline between rows — not under a section's last one
            visible: row.ListView.nextSection === row.ListView.section
            x: 36
            anchors.bottom: parent.bottom
            width: parent.width - x - 16
            height: 1
            color: theme.divider
        }
    }
}
