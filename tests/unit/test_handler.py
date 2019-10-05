from autoblock_function import app
import requests, pytest, json, datetime, os


@pytest.fixture()
def message_event():
    return json.load(open('events/message.json'))


@pytest.fixture()
def new_member_event():
    return json.load(open('events/new_member.json'))


@pytest.fixture()
def ssm_configuration():
    return {
        'Parameters': [{
            'Name': '/autoblock_bot/bot_key',
            'Type': 'String',
            'Value': 'SECRET_KEY',
            'Version': 1,
            'LastModifiedDate': datetime.datetime(2019, 10, 2, 19, 53, 0, 423000),
            'ARN': 'arn:aws:ssm:us-west-2:999999999999:parameter/autoblock_bot/bot_key'
        }]
    }

@pytest.fixture()
def banned_user_response():
    return {
        'Items': [{'pk': {'S': 'user_999999402'}, 'username': {'S': '@testuser'}}],
        'Count': 1,
        'ScannedCount': 1
    }


@pytest.fixture()
def non_banned_user_response():
    return {
        'Items': [],
        'Count': 0,
        'ScannedCount': 0
    }

@pytest.fixture()
def mock_setup(ssm_configuration, mocker):
    os.environ['APP_CONFIG_PATH'] = '/autoblock_bot'
    os.environ['TABLE_NAME'] = 'test_table'

    mocker.patch('autoblock_function.app.ssm.get_parameters_by_path')
    mocker.patch('autoblock_function.app.dynamodb.query')
    mocker.patch('requests.post')

    app.ssm.get_parameters_by_path.return_value = ssm_configuration


def test_message_event(message_event, mock_setup):
    ret = app.lambda_handler(message_event, "")

    assert ret['statusCode'] == 200
    assert app.dynamodb.query.call_count == 0
    assert requests.post.call_count == 0


def test_non_banned_user(new_member_event, non_banned_user_response, mock_setup):
    app.dynamodb.query.return_value = non_banned_user_response

    ret = app.lambda_handler(new_member_event, "")
    
    assert ret['statusCode'] == 200
    assert app.dynamodb.query.call_count == 1
    assert requests.post.call_count == 0


def test_ban_user(new_member_event, banned_user_response, mock_setup):
    app.dynamodb.query.return_value = banned_user_response

    ret = app.lambda_handler(new_member_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.query.assert_called_once_with(
        TableName='test_table',
        ExpressionAttributeValues={
            ':pk': {'S': 'user_999999402'}
        },
        KeyConditionExpression='pk = :pk'
    )
    requests.post.assert_called_once_with(
        'https://api.telegram.org/botSECRET_KEY/kickChatMember',
        data={
            'chat_id': -1009999992388,
            'user_id': 999999402
        }
    )
