// One tracked thing, two lines tall:
//   ● Name                        2h
//     27.0 beta 5 · iOS
// The dot means "there's something to install"; it carries the accent only
// while the news is fresh, the same three states as the desktop card (fresh /
// pending-but-old / current). Tap → the detail sheet. Swipe right → mark
// updated (only when there IS an update).
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
    required property bool fresh

    signal opened()
    signal markUpdated()

    objectName: "row_" + name
    width: ListView.view ? ListView.view.width : 360
    height: 64
    padding: 0
    focusPolicy: Qt.NoFocus
    hoverEnabled: false
    swipe.enabled: hasUpdate
    onClicked: if (swipe.position === 0) row.opened()
    swipe.onCompleted: row.markUpdated()

    readonly property color nameColour: fresh ? theme.text : (hasUpdate ? theme.text : theme.textDim)

    background: Rectangle {
        color: row.pressed && row.swipe.position === 0 ? theme.surface : theme.background
    }

    // revealed under the row as it slides right
    swipe.left: Rectangle {
        width: row.width
        height: row.height
        color: theme.accent
        Row {
            anchors.verticalCenter: parent.verticalCenter
            x: 20
            spacing: 10
            Icon { anchors.verticalCenter: parent.verticalCenter; name: "check"; tint: theme.onAccent; size: 22 }
            Label {
                anchors.verticalCenter: parent.verticalCenter
                text: qsTr("Mark updated")
                color: theme.onAccent
                font.pixelSize: 15
                font.weight: Font.DemiBold
            }
        }
    }

    contentItem: Item {
        // the dot column — kept even when empty so names line up
        Rectangle {
            id: dot
            x: 18
            y: 18
            width: 9
            height: 9
            radius: 4.5
            visible: row.hasUpdate
            color: row.fresh ? theme.accent : theme.textFaint
        }
        Label {
            id: nameLabel
            x: 38
            y: 10
            width: parent.width - x - ageLabel.width - 28 - (newBadge.visible ? newBadge.width + 8 : 0)
            text: row.name
            color: row.nameColour
            font.pixelSize: 16
            font.weight: row.hasUpdate ? Font.DemiBold : Font.Normal
            elide: Text.ElideRight
        }
        Label {
            id: newBadge
            visible: row.isNew
            anchors.left: nameLabel.right
            anchors.leftMargin: 8
            anchors.baseline: nameLabel.baseline
            text: qsTr("NEW")
            color: row.fresh ? theme.accent : theme.textFaint
            font.pixelSize: 11
            font.weight: Font.Bold
            font.letterSpacing: 0.8
        }
        Label {
            id: ageLabel
            anchors.right: parent.right
            anchors.rightMargin: 18
            anchors.baseline: nameLabel.baseline
            text: row.age
            color: theme.textDim
            font.pixelSize: 13
        }
        Label {
            x: 38
            y: 35
            width: parent.width - x - 18
            text: row.error !== ""
                  ? row.error
                  : row.versionLine + (row.platform ? "  ·  " + row.platform : "")
            color: row.error !== "" ? theme.warning
                   : (row.hasUpdate && row.fresh ? theme.accent : theme.textDim)
            font.pixelSize: 14
            elide: Text.ElideRight
        }
        Rectangle {  // hairline between rows
            x: 38
            anchors.bottom: parent.bottom
            width: parent.width - x
            height: 1
            color: theme.divider
        }
    }
}
