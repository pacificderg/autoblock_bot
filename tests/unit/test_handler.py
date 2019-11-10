from autoblock_function import app
import requests, pytest, json, datetime, os


TEST_USER_ID=99999999


@pytest.fixture()
def message_event():
    return json.load(open('events/message.json'))


@pytest.fixture()
def new_member_event():
    return json.load(open('events/new_member.json'))


@pytest.fixture()
def unknown_command_event():
    return json.load(open('events/unknown_command.json'))


@pytest.fixture()
def is_banned_command_event():
    return json.load(open('events/isbanned_command.json'))


@pytest.fixture()
def public_command_event():
    return json.load(open('events/public_command.json'))


@pytest.fixture()
def ban_command_event():
    return json.load(open('events/ban_command.json'))


@pytest.fixture()
def unban_command_event():
    return json.load(open('events/unban_command.json'))
    

@pytest.fixture()
def ssm_configuration():
    return {
        'Parameters': [{
            'Name': '/autoblock_bot/bot_key',
            'Value': 'SECRET_KEY',
        }, {
            'Name': '/autoblock_bot/api_id',
            'Value': 'API_ID'
        }, {
            'Name': '/autoblock_bot/api_hash',
            'Value': 'API_HASH'
        }]
    }

@pytest.fixture()
def broken_ssm_configuration():
    return {
        'Parameters': []
    }

@pytest.fixture()
def banned_user_response():
    return {
        'Item': {'pk': {'S': 'user_999999402'}, 'username': {'S': '@testuser'}},
    }


@pytest.fixture()
def non_banned_user_response():
    return {}


@pytest.fixture()
def admin_user_response():
    return {
        'Item': {'pk': {'S': 'user_999999999'}, 'username': {'S': '@testuser'}},
    }


@pytest.fixture()
def non_admin_user_response():
    return {}


@pytest.fixture()
def mock_setup(ssm_configuration, mocker):
    os.environ['APP_CONFIG_PATH'] = '/autoblock_bot'
    os.environ['TABLE_NAME'] = 'test_table'

    mocker.patch('autoblock_function.app.ssm.get_parameters_by_path')
    mocker.patch('autoblock_function.app.dynamodb.get_item')
    mocker.patch('autoblock_function.app.dynamodb.put_item')
    mocker.patch('autoblock_function.app.dynamodb.delete_item')
    mocker.patch('requests.post')
    mocker.patch('autoblock_function.app.TelegramClient')

    app.ssm.get_parameters_by_path.return_value = ssm_configuration
    app.client = None


@pytest.fixture()
def mock_bad_setup(broken_ssm_configuration, mock_setup):
    app.ssm.get_parameters_by_path.return_value = broken_ssm_configuration


@pytest.fixture()
def telegram_test_user_entity(mocker):
    client_mock = mocker.Mock(spec=['start', 'get_entity'])
    client_mock.get_entity.return_value = mocker.Mock(id=TEST_USER_ID)
    return client_mock


def test_bad_ssm_config(message_event, mock_bad_setup):
    with pytest.raises(Exception):
        app.lambda_handler(message_event, "")

    assert app.config is None


def test_message_event(message_event, mock_setup):
    # pylint: disable=no-member
    ret = app.lambda_handler(message_event, "")

    assert ret['statusCode'] == 200
    assert app.dynamodb.get_item.call_count == 0
    assert requests.post.call_count == 0


def test_non_banned_user(new_member_event, non_banned_user_response, mock_setup):
    # pylint: disable=no-member
    app.dynamodb.get_item.return_value = non_banned_user_response

    ret = app.lambda_handler(new_member_event, "")
    
    assert ret['statusCode'] == 200
    assert app.dynamodb.get_item.call_count == 1
    assert requests.post.call_count == 0


def test_ban_user(new_member_event, banned_user_response, mock_setup):
    # pylint: disable=no-member
    app.dynamodb.get_item.return_value = banned_user_response

    ret = app.lambda_handler(new_member_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.get_item.assert_called_once_with(
        TableName='test_table',
        Key={
            'pk': {'S': 'user_999999402'}
        }
    )
    requests.post.assert_called_once_with(
        'https://api.telegram.org/botSECRET_KEY/kickChatMember',
        data={
            'chat_id': -1009999992388,
            'user_id': 999999402
        }
    )


def test_unknown_command(
    unknown_command_event,
    admin_user_response,
    mock_setup
):
    # pylint: disable=no-member
    app.dynamodb.get_item.return_value = admin_user_response

    ret = app.lambda_handler(unknown_command_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.get_item.assert_called_once_with(
        TableName='test_table',
        Key={'pk': {'S': 'admin_99999999'}}
    )
    requests.post.assert_called_once_with(
        'https://api.telegram.org/botSECRET_KEY/sendMessage',
        data={
            'chat_id': 99999999,
            'reply_to_message_id': 13,
            'text': 'Unknown command'
        }
    )


def test_command(
    is_banned_command_event,
    admin_user_response,
    banned_user_response,
    telegram_test_user_entity,
    mocker,
    mock_setup
):
    # pylint: disable=no-member
    app.dynamodb.get_item.side_effect = [admin_user_response, banned_user_response]
    app.TelegramClient.return_value = telegram_test_user_entity

    ret = app.lambda_handler(is_banned_command_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.get_item.assert_has_calls([
        mocker.call(
            TableName='test_table',
            Key={'pk': {'S': 'admin_99999999'}}
        ),
        mocker.call(
            TableName='test_table',
            Key={'pk': {'S': 'user_{}'.format(TEST_USER_ID)}}
        )
    ])
    app.client.get_entity.assert_called_once_with('@test_user')
    requests.post.assert_called_once_with(
        'https://api.telegram.org/botSECRET_KEY/sendMessage',
        data={
            'chat_id': 99999999,
            'reply_to_message_id': 13,
            'text': '@test_user ({}) is banned'.format(TEST_USER_ID)
        }
    )


def test_public_command(public_command_event, mock_setup):
    # pylint: disable=no-member
    ret = app.lambda_handler(public_command_event, "")

    assert ret['statusCode'] == 200
    assert app.dynamodb.get_item.call_count == 0
    assert requests.post.call_count == 0


def test_command_from_non_admin(is_banned_command_event, non_admin_user_response, mock_setup):
    # pylint: disable=no-member
    app.dynamodb.get_item.return_value = non_admin_user_response

    ret = app.lambda_handler(is_banned_command_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.get_item.assert_called_once_with(
        TableName='test_table',
        Key={'pk': {'S': 'admin_99999999'}}
    )
    assert requests.post.call_count == 0


def test_ban_command(
    ban_command_event,
    admin_user_response,
    non_banned_user_response,
    telegram_test_user_entity,
    mocker,
    mock_setup
):
    # pylint: disable=no-member
    app.dynamodb.get_item.side_effect = [admin_user_response, non_banned_user_response]
    app.TelegramClient.return_value = telegram_test_user_entity

    ret = app.lambda_handler(ban_command_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.get_item.assert_has_calls([
        mocker.call(
            TableName='test_table',
            Key={'pk': {'S': 'admin_99999999'}}
        ),
        mocker.call(
            TableName='test_table',
            Key={'pk': {'S': 'user_{}'.format(TEST_USER_ID)}}
        )
    ])
    app.client.get_entity.assert_called_once_with('@test_user')
    app.dynamodb.put_item.assert_called_once_with(
        TableName='test_table',
        Item={
            'pk': {'S': 'user_{}'.format(TEST_USER_ID)},
            'username': {'S': '@test_user'},
        }
    )
    requests.post.assert_called_once_with(
        'https://api.telegram.org/botSECRET_KEY/sendMessage',
        data={
            'chat_id': 99999999,
            'reply_to_message_id': 13,
            'text': '@test_user ({}) has been banned'.format(TEST_USER_ID)
        }
    )


def test_ban_command_banned_user(
    ban_command_event,
    admin_user_response,
    banned_user_response,
    telegram_test_user_entity,
    mocker,
    mock_setup
):
    # pylint: disable=no-member
    app.dynamodb.get_item.side_effect = [admin_user_response, banned_user_response]
    app.TelegramClient.return_value = telegram_test_user_entity

    ret = app.lambda_handler(ban_command_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.get_item.assert_has_calls([
        mocker.call(
            TableName='test_table',
            Key={'pk': {'S': 'admin_99999999'}}
        ),
        mocker.call(
            TableName='test_table',
            Key={'pk': {'S': 'user_{}'.format(TEST_USER_ID)}}
        )
    ])
    app.client.get_entity.assert_called_once_with('@test_user')
    assert app.dynamodb.put_item.call_count == 0
    requests.post.assert_called_once_with(
        'https://api.telegram.org/botSECRET_KEY/sendMessage',
        data={
            'chat_id': 99999999,
            'reply_to_message_id': 13,
            'text': '@test_user ({}) is already banned'.format(TEST_USER_ID)
        }
    )


def test_unban_command(
    unban_command_event,
    admin_user_response,
    banned_user_response,
    telegram_test_user_entity,
    mocker,
    mock_setup
):
    # pylint: disable=no-member
    app.dynamodb.get_item.side_effect = [admin_user_response, banned_user_response]
    app.TelegramClient.return_value = telegram_test_user_entity

    ret = app.lambda_handler(unban_command_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.get_item.assert_has_calls([
        mocker.call(
            TableName='test_table',
            Key={'pk': {'S': 'admin_99999999'}}
        ),
        mocker.call(
            TableName='test_table',
            Key={'pk': {'S': 'user_{}'.format(TEST_USER_ID)}}
        )
    ])
    app.client.get_entity.assert_called_once_with('@test_user')
    app.dynamodb.delete_item.assert_called_once_with(
        TableName='test_table',
        Key={'pk': {'S': 'user_{}'.format(TEST_USER_ID)}}
    )
    requests.post.assert_called_once_with(
        'https://api.telegram.org/botSECRET_KEY/sendMessage',
        data={
            'chat_id': 99999999,
            'reply_to_message_id': 13,
            'text': '@test_user ({}) has been unbanned'.format(TEST_USER_ID)
        }
    )


def test_unban_command_nonbanned_user(
    unban_command_event,
    admin_user_response,
    non_banned_user_response,
    telegram_test_user_entity,
    mocker,
    mock_setup
):
    # pylint: disable=no-member
    app.dynamodb.get_item.side_effect = [admin_user_response, non_banned_user_response]
    app.TelegramClient.return_value = telegram_test_user_entity

    ret = app.lambda_handler(unban_command_event, "")

    assert ret['statusCode'] == 200
    app.dynamodb.get_item.assert_has_calls([
        mocker.call(
            TableName='test_table',
            Key={'pk': {'S': 'admin_99999999'}}
        ),
        mocker.call(
            TableName='test_table',
            Key={'pk': {'S': 'user_{}'.format(TEST_USER_ID)}}
        )
    ])
    app.client.get_entity.assert_called_once_with('@test_user')
    assert app.dynamodb.delete_item.call_count == 0
    requests.post.assert_called_once_with(
        'https://api.telegram.org/botSECRET_KEY/sendMessage',
        data={
            'chat_id': 99999999,
            'reply_to_message_id': 13,
            'text': '@test_user ({}) is not banned'.format(TEST_USER_ID)
        }
    )
 