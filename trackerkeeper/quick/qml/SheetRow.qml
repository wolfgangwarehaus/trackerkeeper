// A full-width, 52 px row in a bottom sheet: optional icon, label, an
// optional trailing count, and a check when it's the current choice.
import QtQuick
import QtQuick.Controls

ItemDelegate {
    id: row
    property string iconName: ""
    property bool current: false
    property int count: -1          // < 0 = none
    width: parent ? parent.width : 300
    height: 52
    focusPolicy: Qt.NoFocus
    hoverEnabled: false
    leftPadding: 4
    rightPadding: 4
    background: Rectangle { radius: 10; color: theme.text; opacity: row.pressed ? 0.08 : 0 }
    contentItem: Item {
        Icon {
            id: lead
            visible: row.iconName !== ""
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            name: row.iconName
            size: 22
            tint: theme.text
        }
        Label {
            anchors.left: lead.visible ? lead.right : parent.left
            anchors.leftMargin: lead.visible ? 16 : 0
            anchors.right: trail.left
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            text: row.text
            color: theme.text
            font.pixelSize: 16
            font.weight: row.current ? Font.DemiBold : Font.Normal
            elide: Text.ElideRight
        }
        Row {
            id: trail
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 12
            Label {
                anchors.verticalCenter: parent.verticalCenter
                visible: row.count >= 0
                text: row.count
                color: theme.textFaint
                font.pixelSize: 14
            }
            Icon {
                anchors.verticalCenter: parent.verticalCenter
                name: "check"
                size: 20
                tint: theme.text
                opacity: row.current ? 1 : 0     // keeps the counts aligned
            }
        }
    }
}
